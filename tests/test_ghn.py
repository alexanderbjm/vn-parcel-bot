import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from vn_parcel_bot.carriers.ghn import (
    GHN_TRACKING_URL,
    GhnCarrier,
    ghn_phone_verify,
    parse_ghn_response,
)
from vn_parcel_bot.carriers.models import CarrierError

FIXTURES = Path(__file__).parent / "fixtures" / "ghn"
VN = ZoneInfo("Asia/Ho_Chi_Minh")
CODE = "GA0000000001"


def load_json(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def test_phone_verify_vector():
    assert ghn_phone_verify(CODE, "1234") == hashlib.sha256(b"GA0000000001|1234").hexdigest()


def test_parse_in_transit():
    result = parse_ghn_response(load_json("in_transit"), CODE)
    assert result.found
    assert (result.carrier, result.tracking_number) == ("ghn", CODE)
    assert len(result.events) == 3
    times = [e.time for e in result.events]
    assert times == sorted(times)
    assert result.latest.description == "Đang giao hàng"
    assert result.latest.raw_status == "delivering"
    sorting = result.events[1]
    assert (sorting.description, sorting.location) == ("Đang phân loại hàng", None)
    assert result.events[0].location == "Bưu cục Cầu Giấy, Hà Nội"
    assert result.events[0].time.astimezone(VN).strftime("%d/%m %H:%M") == "10/09 10:15"
    assert not result.delivered
    assert not result.returned


def test_parse_delivered():
    result = parse_ghn_response(load_json("delivered"), "GA0000000002")
    assert result.delivered is True
    assert result.returned is False


def test_parse_returned_order_status():
    payload = load_json("in_transit")
    payload["data"]["order_info"]["status"] = "returned"
    result = parse_ghn_response(payload, CODE)
    assert result.returned is True
    assert result.delivered is False


def test_parse_delivered_from_latest_log():
    payload = load_json("in_transit")
    payload["data"]["order_info"] = {}
    payload["data"]["tracking_logs"][0]["status"] = "delivered"
    assert parse_ghn_response(payload, CODE).delivered is True


def test_parse_unknown_status_uses_raw_code():
    payload = load_json("in_transit")
    payload["data"]["tracking_logs"][0] = {
        "status": "brand_new_status",
        "action_at": "2026-09-11T02:00:00Z",
    }
    assert parse_ghn_response(payload, CODE).latest.description == "brand_new_status"


def test_parse_code_400_not_found():
    assert parse_ghn_response(load_json("not_found"), CODE).found is False


def test_parse_code_500_http_status():
    with pytest.raises(CarrierError) as exc:
        parse_ghn_response({"code": 500, "message": "error", "data": None}, CODE)
    assert exc.value.reason == "http_status"


def test_parse_empty_logs_not_found():
    payload = load_json("in_transit")
    payload["data"]["tracking_logs"] = []
    assert parse_ghn_response(payload, CODE).found is False


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"code": 200, "data": None},
        {"code": 200, "data": {"tracking_logs": "x"}},
        {"code": 200, "data": {"tracking_logs": [{"status": "picked"}]}},
    ],
)
def test_parse_malformed_raises(payload):
    with pytest.raises(CarrierError) as exc:
        parse_ghn_response(payload, CODE)
    assert exc.value.reason == "parse"


@respx.mock
async def test_fetch_posts_code_and_hash():
    route = respx.post(GHN_TRACKING_URL).mock(
        return_value=httpx.Response(200, json=load_json("in_transit"))
    )
    async with httpx.AsyncClient() as http:
        result = await GhnCarrier().fetch(http, CODE, "1234")
    assert json.loads(route.calls.last.request.content) == {
        "order_code": CODE,
        "phone_verify": ghn_phone_verify(CODE, "1234"),
    }
    assert result.found


@respx.mock
async def test_fetch_400_phone_verify_fail_is_not_found():
    respx.post(GHN_TRACKING_URL).mock(return_value=httpx.Response(400, json=load_json("not_found")))
    async with httpx.AsyncClient() as http:
        result = await GhnCarrier().fetch(http, CODE, "9999")
    assert result.found is False


@respx.mock
async def test_fetch_400_non_json_http_status():
    respx.post(GHN_TRACKING_URL).mock(return_value=httpx.Response(400, text="bad request"))
    async with httpx.AsyncClient() as http:
        with pytest.raises(CarrierError) as exc:
            await GhnCarrier().fetch(http, CODE, "1234")
    assert exc.value.reason == "http_status"


async def test_fetch_requires_phone():
    async with httpx.AsyncClient() as http:
        with pytest.raises(ValueError):
            await GhnCarrier().fetch(http, CODE, None)


@respx.mock
async def test_fetch_maps_errors():
    respx.post(GHN_TRACKING_URL).mock(return_value=httpx.Response(403))
    async with httpx.AsyncClient() as http:
        with pytest.raises(CarrierError) as exc:
            await GhnCarrier().fetch(http, CODE, "1234")
    assert exc.value.reason == "blocked"


def test_carrier_attributes():
    carrier = GhnCarrier()
    assert (carrier.code, carrier.display_name, carrier.needs_phone) == ("ghn", "GHN", True)
