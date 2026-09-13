import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from vn_parcel_bot.carriers.cainiao import (
    CAINIAO_TRACKING_URL,
    CainiaoCarrier,
    parse_cainiao_response,
)
from vn_parcel_bot.carriers.models import CarrierError

FIXTURES = Path(__file__).parent / "fixtures" / "cainiao"
VN = ZoneInfo("Asia/Ho_Chi_Minh")
CODE = "LP00000000000001"


def load_json(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def test_parse_in_transit():
    result = parse_cainiao_response(load_json("in_transit"), CODE)
    assert result.found
    assert (result.carrier, result.tracking_number) == ("cainiao", CODE)
    assert len(result.events) == 4
    times = [e.time for e in result.events]
    assert times == sorted(times)
    assert result.latest.description == "Đã đến trung tâm phân loại tại Việt Nam"
    assert result.latest.raw_status == "GTMS_SC_ARRIVE"
    assert result.events[0].time.astimezone(VN).strftime("%d/%m %H:%M") == "08/09 21:10"
    assert not result.delivered
    assert not result.returned


def test_parse_item_without_time_uses_timestr_and_zone():
    result = parse_cainiao_response(load_json("in_transit"), CODE)
    customs = next(e for e in result.events if e.description == "Đã thông quan nhập khẩu")
    assert customs.time.astimezone(UTC) == datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def test_parse_delivered():
    result = parse_cainiao_response(load_json("delivered"), "LP00000000000002")
    assert result.delivered is True
    assert result.returned is False


def test_parse_returned_action_code():
    payload = load_json("in_transit")
    payload["module"][0]["detailList"][0]["actionCode"] = "GTMS_RETURN_SIGNED"
    result = parse_cainiao_response(payload, CODE)
    assert result.returned is True
    assert result.delivered is False


def test_parse_not_found_verified_body():
    result = parse_cainiao_response(load_json("not_found"), "LP00000000000000")
    assert result.found is False
    assert result.events == ()


@pytest.mark.parametrize(
    "payload",
    [
        {"module": [{"detailList": []}], "success": False},
        {"module": [], "success": True},
        {"success": True},
        [],
    ],
)
def test_parse_bad_envelope_raises(payload):
    with pytest.raises(CarrierError) as exc:
        parse_cainiao_response(payload, CODE)
    assert exc.value.reason == "parse"


def test_parse_item_without_description_raises():
    payload = load_json("in_transit")
    item = payload["module"][0]["detailList"][0]
    item["desc"] = ""
    item["standerdDesc"] = ""
    with pytest.raises(CarrierError) as exc:
        parse_cainiao_response(payload, CODE)
    assert exc.value.reason == "parse"


def test_parse_item_without_any_time_raises():
    payload = load_json("in_transit")
    item = payload["module"][0]["detailList"][0]
    del item["time"]
    del item["timeStr"]
    with pytest.raises(CarrierError) as exc:
        parse_cainiao_response(payload, CODE)
    assert exc.value.reason == "parse"


def test_parse_description_falls_back_to_standerd_desc():
    payload = load_json("in_transit")
    payload["module"][0]["detailList"][0]["desc"] = ""
    result = parse_cainiao_response(payload, CODE)
    assert result.latest.description == "Arrived at sorting center in destination country"


@respx.mock
async def test_fetch_sends_params():
    route = respx.get(url__startswith=CAINIAO_TRACKING_URL).mock(
        return_value=httpx.Response(200, json=load_json("in_transit"))
    )
    async with httpx.AsyncClient() as http:
        result = await CainiaoCarrier().fetch(http, CODE)
    params = route.calls.last.request.url.params
    assert (params["mailNos"], params["lang"], params["language"]) == (CODE, "en-US", "en-US")
    assert result.found


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (httpx.Response(403), "blocked"),
        (httpx.Response(200, text="<html>maintenance</html>"), "blocked"),
    ],
)
@respx.mock
async def test_fetch_maps_errors(response, reason):
    respx.get(url__startswith=CAINIAO_TRACKING_URL).mock(return_value=response)
    async with httpx.AsyncClient() as http:
        with pytest.raises(CarrierError) as exc:
            await CainiaoCarrier().fetch(http, CODE)
    assert exc.value.reason == reason


@respx.mock
async def test_fetch_network_error():
    respx.get(url__startswith=CAINIAO_TRACKING_URL).mock(side_effect=httpx.ConnectTimeout("t"))
    async with httpx.AsyncClient() as http:
        with pytest.raises(CarrierError) as exc:
            await CainiaoCarrier().fetch(http, CODE)
    assert exc.value.reason == "network"


def test_carrier_attributes():
    carrier = CainiaoCarrier()
    assert (carrier.code, carrier.display_name, carrier.needs_phone) == (
        "cainiao",
        "Cainiao",
        False,
    )
