import httpx
import pytest
import respx

from vn_parcel_bot.carriers.aftership import (
    TRACKINGS_URL,
    AfterShipCarrier,
)
from vn_parcel_bot.carriers.models import CarrierError

CODE = "JNTXB000000000001"


def tracking_body(tag: str, checkpoints: list[dict]) -> dict:
    return {
        "meta": {"code": 200},
        "data": {
            "tracking": {
                "tracking_number": CODE,
                "tag": tag,
                "checkpoints": checkpoints,
            }
        },
    }


def scan(message: str, location: str | None = None, at: str = "2026-09-16T01:26:08+00:00") -> dict:
    return {"message": message, "location": location, "checkpoint_time": at}


async def fetch(payload: dict, status: int = 200):
    respx.get(url__startswith=TRACKINGS_URL).mock(return_value=httpx.Response(status, json=payload))
    carrier = AfterShipCarrier(api_key="k")
    async with httpx.AsyncClient() as http:
        return await carrier.fetch(http, CODE)


@respx.mock
async def test_in_transit_tracking_becomes_events():
    result = await fetch(tracking_body("InTransit", [scan("Rời kho Thâm Quyến", "Shenzhen")]))
    assert result.found is True
    assert result.carrier == "aftership"
    assert len(result.events) == 1
    assert result.latest.description == "Rời kho Thâm Quyến"
    assert result.latest.location == "Shenzhen"
    assert result.delivered is False
    assert result.returned is False


@respx.mock
async def test_chinese_wording_is_translated_but_identity_keeps_the_original():
    result = await fetch(tracking_body("InTransit", [scan("快件已到达", "东莞市")]))
    event = result.latest
    assert "快件" not in event.description, "shown in Vietnamese"
    assert event.identity is not None and "快件" in event.identity, "identified by what was said"


@respx.mock
async def test_delivered_and_returned_tags():
    delivered = await fetch(tracking_body("Delivered", [scan("Giao hàng thành công", "Hà Nội")]))
    assert delivered.delivered is True
    returned = await fetch(tracking_body("Exception", [scan("Hoàn hàng", "Hà Nội")]))
    assert returned.returned is True


@respx.mock
async def test_nothing_known_yet_is_not_found():
    result = await fetch(tracking_body("Pending", []))
    assert result.found is False
    assert result.events == ()


@respx.mock
async def test_rate_limited_reads_as_blocked_so_the_quota_gate_applies():
    with pytest.raises(CarrierError) as raised:
        await fetch({"meta": {"code": 429, "message": "too many requests"}}, status=429)
    assert raised.value.reason == "blocked"


@respx.mock
async def test_a_broken_body_is_a_parse_error_not_a_crash():
    with pytest.raises(CarrierError) as raised:
        await fetch({"meta": {"code": 200}, "data": {}})
    assert raised.value.reason == "parse"
