import json
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from vn_parcel_bot.carriers.models import CarrierError
from vn_parcel_bot.carriers.ninjavan import (
    NINJAVAN_TRACKING_URL,
    NinjaVanCarrier,
    parse_ninjavan_response,
)

FIXTURES = Path(__file__).parent / "fixtures" / "ninjavan"
VN = ZoneInfo("Asia/Ho_Chi_Minh")
CODE = "SPEVN000000000001"


def load_json(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def local(dt) -> str:
    return dt.astimezone(VN).strftime("%d/%m %H:%M")


def test_parse_in_transit_snake_case():
    result = parse_ninjavan_response(load_json("in_transit"), CODE)
    assert result.found
    assert (result.carrier, result.tracking_number) == ("ninjavan", CODE)
    assert len(result.events) == 4
    times = [e.time for e in result.events]
    assert times == sorted(times)
    assert result.latest.description == "Giao hàng thất bại – Không liên lạc được với khách hàng"
    assert result.latest.raw_status == "DELIVERY_FAILURE"
    hub = next(e for e in result.events if e.raw_status == "ARRIVED_AT_DESTINATION_HUB")
    assert (hub.description, hub.location) == ("Đã đến kho giao", "Kho Hồ Chí Minh")
    assert local(result.events[0].time) == "10/09 09:30"
    assert not result.delivered
    assert not result.returned


def test_parse_delivered_camel_case_epoch_ms():
    result = parse_ninjavan_response(load_json("delivered"), "SPEVN000000000002")
    assert result.delivered is True
    assert result.returned is False
    assert len(result.events) == 3
    assert local(result.events[0].time) == "11/09 20:00"
    assert (result.events[0].description, result.events[0].location) == (
        "Đã nhập kho",
        "Kho Hồ Chí Minh",
    )


def test_parse_returned_granular_status():
    result = parse_ninjavan_response(load_json("returned"), "SPEVN000000000003")
    assert result.returned is True
    assert result.delivered is False
    assert result.latest.description == "Giao hàng thành công"
    assert local(result.events[0].time) == "12/09 15:00"
    assert any(e.description == "Đang hoàn hàng về người gửi" for e in result.events)


def test_parse_unknown_type_capitalized():
    payload = {"events": [{"type": "SOME_NEW_TYPE", "time": "2026-09-10T10:00:00Z", "data": {}}]}
    assert parse_ninjavan_response(payload, CODE).latest.description == "Some new type"


def test_parse_failure_reason_falls_back_to_english():
    payload = {
        "events": [
            {
                "type": "DELIVERY_FAILURE",
                "time": "2026-09-10T10:00:00Z",
                "data": {"failureReason": {"en": "Address not found"}},
            }
        ]
    }
    description = parse_ninjavan_response(payload, CODE).latest.description
    assert description == "Giao hàng thất bại – Address not found"


def test_parse_naive_iso_time_is_vietnam_local():
    payload = {"events": [{"type": "RESUME", "time": "2026-09-10T10:00:00", "data": {}}]}
    assert local(parse_ninjavan_response(payload, CODE).latest.time) == "10/09 10:00"


def test_parse_empty_events_not_found():
    assert parse_ninjavan_response({"events": []}, CODE).found is False


@pytest.mark.parametrize("payload", [{"tracking_id": CODE}, {"events": "x"}, []])
def test_parse_missing_events_raises(payload):
    with pytest.raises(CarrierError) as exc:
        parse_ninjavan_response(payload, CODE)
    assert exc.value.reason == "parse"


def test_parse_data_wrapper_unwrapped():
    result = parse_ninjavan_response({"data": load_json("delivered")}, "SPEVN000000000002")
    assert result.found
    assert result.delivered


@pytest.mark.parametrize(
    "event",
    [{"type": "HUB_INBOUND_SCAN", "data": {}}, {"time": "2026-09-10T10:00:00Z", "data": {}}],
)
def test_parse_event_without_time_or_type_raises(event):
    with pytest.raises(CarrierError) as exc:
        parse_ninjavan_response({"events": [event]}, CODE)
    assert exc.value.reason == "parse"


@respx.mock
async def test_fetch_404_not_found_code():
    respx.get(url__startswith=NINJAVAN_TRACKING_URL).mock(
        return_value=httpx.Response(404, json=load_json("not_found"))
    )
    async with httpx.AsyncClient() as http:
        result = await NinjaVanCarrier().fetch(http, CODE)
    assert result.found is False


@respx.mock
async def test_fetch_404_other_error_http_status():
    respx.get(url__startswith=NINJAVAN_TRACKING_URL).mock(
        return_value=httpx.Response(404, json={"error": {"code": 999}})
    )
    async with httpx.AsyncClient() as http:
        with pytest.raises(CarrierError) as exc:
            await NinjaVanCarrier().fetch(http, CODE)
    assert exc.value.reason == "http_status"


@respx.mock
async def test_fetch_sends_tracking_id_param():
    route = respx.get(url__startswith=NINJAVAN_TRACKING_URL).mock(
        return_value=httpx.Response(200, json=load_json("in_transit"))
    )
    async with httpx.AsyncClient() as http:
        result = await NinjaVanCarrier().fetch(http, CODE)
    assert route.calls.last.request.url.params["tracking_id"] == CODE
    assert result.found


@respx.mock
async def test_fetch_maps_errors():
    respx.get(url__startswith=NINJAVAN_TRACKING_URL).mock(return_value=httpx.Response(403))
    async with httpx.AsyncClient() as http:
        with pytest.raises(CarrierError) as blocked:
            await NinjaVanCarrier().fetch(http, CODE)
    assert blocked.value.reason == "blocked"


def test_carrier_attributes():
    carrier = NinjaVanCarrier()
    assert (carrier.code, carrier.display_name, carrier.needs_phone) == (
        "ninjavan",
        "Ninja Van",
        False,
    )
