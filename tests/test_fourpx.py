import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from vn_parcel_bot.carriers.fourpx import (
    FOURPX_TRACKING_URL,
    FourPxCarrier,
    parse_fourpx_response,
)
from vn_parcel_bot.carriers.models import CarrierError

FIXTURES = Path(__file__).parent / "fixtures" / "fourpx"
VN = ZoneInfo("Asia/Ho_Chi_Minh")
CODE = "4PX0000000000000001"


def load_json(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def test_parse_in_transit():
    result = parse_fourpx_response(load_json("in_transit"), CODE)
    assert result.found
    assert (result.carrier, result.tracking_number) == ("fourpx", CODE)
    assert [e.time.astimezone(UTC) for e in result.events] == [
        datetime(2026, 9, 9, 13, 15, tzinfo=UTC),
        datetime(2026, 9, 10, 10, 30, tzinfo=UTC),
        datetime(2026, 9, 11, 3, 0, tzinfo=UTC),
    ]
    assert result.latest.description == "Arrived at destination country delivery center"
    assert result.latest.location == "Ho Chi Minh, VN"
    assert result.latest.raw_status == "FPX_D_AAD"
    assert result.events[0].time.astimezone(VN).strftime("%d/%m %H:%M") == "09/09 20:15"
    assert not result.delivered
    assert not result.returned


def test_parse_delivered():
    result = parse_fourpx_response(load_json("delivered"), "4PX0000000000000002")
    assert result.delivered is True
    assert result.returned is False


def test_parse_not_found_null_tracks():
    result = parse_fourpx_response(load_json("not_found"), "4PX0000000000000000")
    assert result.found is False


def test_parse_not_found_empty_tracks():
    payload = load_json("in_transit")
    payload["data"][0]["tracks"] = []
    assert parse_fourpx_response(payload, CODE).found is False


def test_parse_not_found_empty_data():
    assert parse_fourpx_response({"result": 1, "data": []}, CODE).found is False


@pytest.mark.parametrize("payload", [{"result": 0, "data": []}, {"data": []}, []])
def test_parse_bad_envelope_raises(payload):
    with pytest.raises(CarrierError) as exc:
        parse_fourpx_response(payload, CODE)
    assert exc.value.reason == "parse"


def test_parse_missing_datestr_raises():
    payload = load_json("in_transit")
    del payload["data"][0]["tracks"][0]["tkDateStr"]
    with pytest.raises(CarrierError) as exc:
        parse_fourpx_response(payload, CODE)
    assert exc.value.reason == "parse"


def test_parse_uses_translated_desc_when_desc_blank():
    payload = load_json("in_transit")
    track = payload["data"][0]["tracks"][0]
    track["tkDesc"] = " "
    track["tkTranslatedDesc"] = "Đã đến trung tâm giao hàng"
    assert parse_fourpx_response(payload, CODE).latest.description == "Đã đến trung tâm giao hàng"


def test_parse_bad_timezone_defaults_to_plus_eight():
    payload = load_json("in_transit")
    payload["data"][0]["tracks"][0]["tkTimezone"] = "???"
    latest = parse_fourpx_response(payload, CODE).latest
    assert latest.time.astimezone(UTC) == datetime(2026, 9, 11, 2, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("mutate", "detail"),
    [
        (lambda p: p["data"][0]["tracks"].append("x"), "object"),
        (lambda p: p["data"][0]["tracks"][0].update(tkDateStr="11/09/2026"), "tkDateStr"),
        (lambda p: p["data"][0]["tracks"][0].update(tkDesc="", tkTranslatedDesc=""), "description"),
        (lambda p: p.update(data=["x"]), "data"),
        (lambda p: p["data"][0].update(tracks="x"), "tracks"),
    ],
)
def test_parse_malformed_tracks_raise(mutate, detail):
    payload = load_json("in_transit")
    mutate(payload)
    with pytest.raises(CarrierError) as exc:
        parse_fourpx_response(payload, CODE)
    assert exc.value.reason == "parse"
    assert detail in exc.value.detail


def test_parse_location_blank_is_none():
    payload = load_json("in_transit")
    payload["data"][0]["tracks"][0]["tkLocation"] = ""
    assert parse_fourpx_response(payload, CODE).latest.location is None


@respx.mock
async def test_fetch_posts_json_body():
    route = respx.post(FOURPX_TRACKING_URL).mock(
        return_value=httpx.Response(200, json=load_json("in_transit"))
    )
    async with httpx.AsyncClient() as http:
        result = await FourPxCarrier().fetch(http, CODE)
    assert json.loads(route.calls.last.request.content) == {
        "queryCodes": [CODE],
        "language": "en-us",
        "translateLanguage": "en-us",
    }
    assert result.found


@pytest.mark.parametrize(
    ("response", "reason"),
    [(httpx.Response(429), "blocked"), (httpx.Response(502), "http_status")],
)
@respx.mock
async def test_fetch_maps_errors(response, reason):
    respx.post(FOURPX_TRACKING_URL).mock(return_value=response)
    async with httpx.AsyncClient() as http:
        with pytest.raises(CarrierError) as exc:
            await FourPxCarrier().fetch(http, CODE)
    assert exc.value.reason == reason


def test_carrier_attributes():
    carrier = FourPxCarrier()
    assert (carrier.code, carrier.display_name, carrier.needs_phone) == ("fourpx", "4PX", False)
