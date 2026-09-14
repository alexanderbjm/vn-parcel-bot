import copy
import json
from datetime import UTC, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from vn_parcel_bot.carriers.models import CarrierError
from vn_parcel_bot.carriers.modules.spx import SPX_ORDER_INFO_URL, SpxCarrier, parse_spx_response

FIXTURES = Path(__file__).parent / "fixtures" / "spx"
VN = ZoneInfo("Asia/Ho_Chi_Minh")
CODE = "SPXVN000000000001"
DELIVERED_CODE = "SPXVN000000000002"


def load_json(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def records(payload: dict) -> list[dict]:
    return payload["data"]["sls_tracking_info"]["records"]


def test_parse_in_transit():
    result = parse_spx_response(load_json("in_transit"), CODE)
    assert result.found
    assert (result.carrier, result.tracking_number) == ("spx", CODE)
    assert len(result.events) == 5
    times = [e.time for e in result.events]
    assert times == sorted(times)
    assert all(t.utcoffset() == timedelta(0) for t in times)
    assert result.latest.description == "Đang giao hàng"
    assert result.latest.raw_status == "F600"
    assert not result.delivered
    assert not result.returned


def test_parse_skips_internal_records():
    result = parse_spx_response(load_json("in_transit"), CODE)
    assert [e.raw_status for e in result.events] == ["F000", "F100", "F510", "F599", "F600"]


def test_parse_collapses_whitespace_and_keeps_local_time():
    oldest = parse_spx_response(load_json("in_transit"), CODE).events[0]
    assert oldest.description == "Người bán đang chuẩn bị hàng"
    assert oldest.time.astimezone(VN).strftime("%d/%m %H:%M") == "10/09 07:01"


def test_parse_location_only_when_not_in_description():
    result = parse_spx_response(load_json("in_transit"), CODE)
    assert all(e.location is None for e in result.events)
    payload = load_json("in_transit")
    records(payload)[0]["current_location"]["location_name"] = "  Bưu cục  Quận 1 "
    assert parse_spx_response(payload, CODE).latest.location == "Bưu cục Quận 1"


def test_parse_never_exposes_personal_fields():
    result = parse_spx_response(load_json("delivered"), DELIVERED_CODE)
    shown = " ".join(
        f"{e.description} {e.location or ''} {e.raw_status or ''}" for e in result.events
    )
    for private in ("N***A", "0900000000", "Đường Giả", "10.000000", "000000000000002"):
        assert private not in shown


def test_parse_delivered_by_tracking_code():
    result = parse_spx_response(load_json("delivered"), DELIVERED_CODE)
    assert len(result.events) == 6
    assert result.latest.description == "Giao hàng thành công"
    assert result.latest.raw_status == "F980"
    assert result.delivered is True
    assert result.returned is False


def test_parse_delivered_by_milestone():
    payload = load_json("delivered")
    records(payload)[0]["tracking_code"] = "F981"
    assert parse_spx_response(payload, DELIVERED_CODE).delivered is True


def test_parse_returned_marker():
    payload = load_json("in_transit")
    records(payload)[0].update(
        tracking_code="F999",
        tracking_name="Return To Seller",
        description="Đơn hàng đang được hoàn hàng",
        milestone_code=9,
        milestone_name="Returning",
    )
    result = parse_spx_response(payload, CODE)
    assert result.returned is True
    assert result.delivered is False


def test_parse_not_found_retcode():
    result = parse_spx_response(load_json("not_found"), CODE)
    assert result.found is False
    assert result.events == ()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(data={}),
        lambda p: p["data"].pop("sls_tracking_info"),
        lambda p: p["data"]["sls_tracking_info"].update(records=[]),
        lambda p: [r.update(display_flag=0) for r in records(p)],
    ],
    ids=["empty-data", "no-tracking-info", "empty-records", "only-internal-records"],
)
def test_parse_not_found_shapes(mutate):
    payload = load_json("in_transit")
    mutate(payload)
    assert parse_spx_response(payload, CODE).found is False


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


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p["data"].update(sls_tracking_info="x"),
        lambda p: p["data"]["sls_tracking_info"].update(records="x"),
    ],
    ids=["tracking-info-not-object", "records-not-list"],
)
def test_parse_rejects_malformed_structure(mutate):
    payload = load_json("in_transit")
    mutate(payload)
    with pytest.raises(CarrierError) as exc:
        parse_spx_response(payload, CODE)
    assert exc.value.reason == "parse"


@pytest.mark.parametrize(
    "item",
    [
        "not an object",
        {"display_flag": 1, "description": "no time"},
        {"display_flag": 1, "actual_time": True, "description": "bool time"},
        {"display_flag": 1, "actual_time": "1789084860", "description": "text time"},
        {"display_flag": 1, "actual_time": 1789084860},
        {"display_flag": 1, "actual_time": 1789084860, "description": "   "},
    ],
)
def test_parse_rejects_bad_records(item):
    payload = copy.deepcopy(load_json("in_transit"))
    records(payload).append(item)
    with pytest.raises(CarrierError) as exc:
        parse_spx_response(payload, CODE)
    assert exc.value.reason == "parse"


@respx.mock
async def test_fetch_sends_code_and_language():
    route = respx.get(url__startswith=SPX_ORDER_INFO_URL).mock(
        return_value=httpx.Response(200, json=load_json("in_transit"))
    )
    async with httpx.AsyncClient() as http:
        result = await SpxCarrier().fetch(http, CODE)
    assert result.found
    params = route.calls.last.request.url.params
    assert params["spx_tn"] == CODE
    assert params["language_code"] == "vi"


@pytest.mark.parametrize(
    ("status", "text", "reason"),
    [
        (403, "", "blocked"),
        (429, "", "blocked"),
        (500, "", "http_status"),
        (200, "<html>captcha</html>", "blocked"),
    ],
)
@respx.mock
async def test_fetch_maps_errors(status, text, reason):
    respx.get(url__startswith=SPX_ORDER_INFO_URL).mock(
        return_value=httpx.Response(status, text=text)
    )
    async with httpx.AsyncClient() as http:
        with pytest.raises(CarrierError) as exc:
            await SpxCarrier().fetch(http, CODE)
    assert exc.value.reason == reason
    assert exc.value.carrier == "spx"


@respx.mock
async def test_fetch_network_error():
    respx.get(url__startswith=SPX_ORDER_INFO_URL).mock(side_effect=httpx.ConnectTimeout("t"))
    async with httpx.AsyncClient() as http:
        with pytest.raises(CarrierError) as exc:
            await SpxCarrier().fetch(http, CODE)
    assert exc.value.reason == "network"


def test_carrier_attributes():
    carrier = SpxCarrier()
    assert (carrier.code, carrier.display_name, carrier.needs_phone) == ("spx", "SPX", False)


def test_event_times_are_utc_aware():
    result = parse_spx_response(load_json("delivered"), DELIVERED_CODE)
    assert result.latest.time.tzinfo is UTC
