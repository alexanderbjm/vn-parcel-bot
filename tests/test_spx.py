import copy
import hashlib
import json
from datetime import UTC, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from vn_parcel_bot.carriers.models import CarrierError
from vn_parcel_bot.carriers.spx import (
    SPX_TRACKING_URL,
    SpxCarrier,
    parse_spx_response,
    sign_spx_code,
)

FIXTURES = Path(__file__).parent / "fixtures" / "spx"
VN = ZoneInfo("Asia/Ho_Chi_Minh")
CODE = "SPXVN000000000001"


def load_json(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def test_parse_in_transit():
    result = parse_spx_response(load_json("in_transit"), CODE)
    assert result.found
    assert (result.carrier, result.tracking_number) == ("spx", CODE)
    assert len(result.events) == 4
    times = [e.time for e in result.events]
    assert times == sorted(times)
    assert all(t.utcoffset() == timedelta(0) for t in times)
    assert result.latest.description == "Đơn hàng đang được giao đến bạn"
    assert result.latest.raw_status == "4"
    assert result.latest.location is None
    assert not result.delivered
    assert not result.returned


def test_parse_delivered():
    result = parse_spx_response(load_json("delivered"), "SPXVN000000000002")
    assert result.delivered is True
    assert result.returned is False


def test_parse_returned_marker():
    payload = load_json("in_transit")
    payload["data"]["current_status"] = "Hoàn hàng thành công"
    result = parse_spx_response(payload, CODE)
    assert result.returned is True
    assert result.delivered is False


def test_parse_not_found():
    result = parse_spx_response(load_json("not_found"), CODE)
    assert result.found is False
    assert result.events == ()


def test_parse_missing_tracking_list_is_not_found():
    payload = load_json("in_transit")
    payload["data"]["tracking_list"] = []
    assert parse_spx_response(payload, CODE).found is False


def test_parse_oldest_event_local_time():
    result = parse_spx_response(load_json("in_transit"), CODE)
    assert result.events[0].time.astimezone(VN).strftime("%d/%m %H:%M") == "10/09 08:00"


def test_parse_replaces_literal_newline_sequences():
    result = parse_spx_response(load_json("in_transit"), CODE)
    assert result.events[1].description == "Đơn hàng đã đến kho SOC Hồ Chí Minh"
    payload = {
        "retcode": 0,
        "data": {"tracking_list": [{"timestamp": 1789002000, "message": "Đơn hàng\\nđã đến kho"}]},
    }
    assert parse_spx_response(payload, CODE).latest.description == "Đơn hàng đã đến kho"


@pytest.mark.parametrize("payload", [[], "x", {"message": "no retcode"}])
def test_parse_rejects_unexpected_payload(payload):
    with pytest.raises(CarrierError) as exc:
        parse_spx_response(payload, CODE)
    assert exc.value.reason == "parse"


def test_parse_unknown_retcode():
    with pytest.raises(CarrierError) as exc:
        parse_spx_response({"retcode": 99999, "message": "x", "data": {}}, CODE)
    assert exc.value.reason == "parse"
    assert "99999" in exc.value.detail


def test_parse_rejects_malformed_list():
    payload = load_json("in_transit")
    payload["data"]["tracking_list"] = "x"
    with pytest.raises(CarrierError) as exc:
        parse_spx_response(payload, CODE)
    assert exc.value.reason == "parse"


@pytest.mark.parametrize(
    "item",
    [
        {"message": "no timestamp"},
        {"timestamp": True, "message": "bool timestamp"},
        {"timestamp": 1789002000},
        {"timestamp": 1789002000, "message": "   "},
    ],
)
def test_parse_rejects_bad_items(item):
    payload = copy.deepcopy(load_json("in_transit"))
    payload["data"]["tracking_list"].append(item)
    with pytest.raises(CarrierError) as exc:
        parse_spx_response(payload, CODE)
    assert exc.value.reason == "parse"


def test_sign_spx_code_vector():
    signed = sign_spx_code(CODE, 1757000000, "s3cr3t")
    digest = hashlib.sha256(f"{CODE}1757000000s3cr3t".encode()).hexdigest()
    assert signed == f"{CODE}|1757000000{digest}"
    assert signed.startswith(f"{CODE}|1757000000")
    assert len(signed) == len(CODE) + 1 + 10 + 64


@respx.mock
async def test_fetch_unsigned_sends_plain_code():
    route = respx.get(url__startswith=SPX_TRACKING_URL).mock(
        return_value=httpx.Response(200, json=load_json("in_transit"))
    )
    async with httpx.AsyncClient() as http:
        result = await SpxCarrier(secret=None).fetch(http, CODE)
    assert result.found
    assert route.calls.last.request.url.params["sls_tracking_number"] == CODE


@respx.mock
async def test_fetch_signed_uses_clock():
    route = respx.get(url__startswith=SPX_TRACKING_URL).mock(
        return_value=httpx.Response(200, json=load_json("not_found"))
    )
    carrier = SpxCarrier(secret="s", clock=lambda: 1757000000.9)  # noqa: S106
    async with httpx.AsyncClient() as http:
        await carrier.fetch(http, CODE)
    sent = route.calls.last.request.url.params["sls_tracking_number"]
    assert sent == sign_spx_code(CODE, 1757000000, "s")


@pytest.mark.parametrize(
    ("status", "text", "reason"),
    [(403, "", "blocked"), (500, "", "http_status"), (200, "<html>captcha</html>", "blocked")],
)
@respx.mock
async def test_fetch_maps_errors(status, text, reason):
    respx.get(url__startswith=SPX_TRACKING_URL).mock(return_value=httpx.Response(status, text=text))
    async with httpx.AsyncClient() as http:
        with pytest.raises(CarrierError) as exc:
            await SpxCarrier().fetch(http, CODE)
    assert exc.value.reason == reason
    assert exc.value.carrier == "spx"


@respx.mock
async def test_fetch_network_error():
    respx.get(url__startswith=SPX_TRACKING_URL).mock(side_effect=httpx.ConnectTimeout("t"))
    async with httpx.AsyncClient() as http:
        with pytest.raises(CarrierError) as exc:
            await SpxCarrier().fetch(http, CODE)
    assert exc.value.reason == "network"


def test_carrier_attributes():
    carrier = SpxCarrier()
    assert (carrier.code, carrier.display_name, carrier.needs_phone) == ("spx", "SPX", False)


def test_event_times_are_utc_aware():
    result = parse_spx_response(load_json("delivered"), "SPXVN000000000002")
    assert result.latest.time.tzinfo is UTC
