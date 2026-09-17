import json
from dataclasses import replace

import httpx
import pytest
import respx

from tests.fakes import FakeCarrier, FakeClock, FakeNotifier, fake_registry
from tests.test_poller import T0, USER, add
from vn_parcel_bot.carriers.seventeen_track import GET_TRACK_INFO_URL, SeventeenTrackCarrier
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.poller import Poller

CODE = "773400000000001"


def track_info(number: str, description: str) -> dict:
    return {
        "code": 0,
        "data": {
            "accepted": [
                {
                    "number": number,
                    "carrier": 100003,
                    "latest_status": {"status": "InTransit"},
                    "track_info": {
                        "events": [
                            {
                                "time_utc": "2026-09-14T15:49:00Z",
                                "description": description,
                                "location": "上海市",
                            }
                        ]
                    },
                }
            ],
            "rejected": [],
        },
    }


@respx.mock
async def test_client_without_a_carrier_id_lets_17track_detect_it():
    route = respx.post(GET_TRACK_INFO_URL).mock(
        return_value=httpx.Response(200, json=track_info(CODE, "快件已到达 上海转运中心"))
    )
    carrier = SeventeenTrackCarrier(
        carrier_code="cainiao", display_name="Cainiao", seventeen_carrier_id=None, api_key="k"
    )
    async with httpx.AsyncClient() as http:
        result = await carrier.fetch(http, CODE)
    payload = json.loads(route.calls.last.request.content)
    assert payload == [{"number": CODE}]
    assert result.found is True
    assert "đã đến" in result.latest.description
    assert "快件" not in result.latest.description
    assert result.latest.location == "Thượng Hải"


@pytest.fixture
async def env(tmp_path, settings):
    repo = await Repository.open(tmp_path / "bot.sqlite3")
    try:
        await repo.upsert_user(USER, now=T0, is_allowed=True)
        carrier = FakeCarrier("cainiao")
        notifier = FakeNotifier()

        async def no_sleep(seconds):
            return None

        keyed = replace(settings, seventeen_track_key="k")
        yield repo, carrier, notifier, keyed, no_sleep
    finally:
        await repo.close()


def build(repo, carrier, notifier, settings, no_sleep, seventeen):
    return Poller(
        repo,
        fake_registry({"cainiao": carrier}),
        None,
        notifier,
        settings,
        FakeClock(T0),
        no_sleep,
        lambda: 0.0,
        seventeen=seventeen,
    )


class FakeSeventeen:
    def __init__(self, result=None):
        self.result = result
        self.calls: list[tuple[str, bool]] = []

    async def fetch(self, http, tracking_number, phone_last4=None, *, auto_register=True):
        self.calls.append((tracking_number, auto_register))
        if self.result is None:
            from vn_parcel_bot.carriers.models import TrackingResult

            return TrackingResult(carrier="cainiao", tracking_number=tracking_number, found=False)
        return self.result


async def test_a_parcel_our_carriers_cannot_track_is_registered_once(env):
    repo, carrier, notifier, settings, no_sleep = env
    from tests.fakes import ev, found

    parcel = await add(repo, CODE, "cainiao")
    seventeen = FakeSeventeen(found("cainiao", CODE, ev(0, "Đã đến Thượng Hải")))
    poller = build(repo, carrier, notifier, settings, no_sleep, seventeen)
    await poller.run_cycle()
    assert [number for number, _ in seventeen.calls] == [CODE]
    stored = await repo.get_parcel(parcel.id)
    assert stored.state == "in_transit"
    assert await repo.count_events(parcel.id) == 1
    assert len(notifier.sent) == 1

    await poller.run_cycle()
    assert len(seventeen.calls) == 1, "one registration per parcel, never repeated"


async def test_nothing_on_17track_leaves_the_parcel_pending_without_retrying(env):
    repo, carrier, notifier, settings, no_sleep = env
    parcel = await add(repo, CODE, "cainiao")
    seventeen = FakeSeventeen()
    poller = build(repo, carrier, notifier, settings, no_sleep, seventeen)
    await poller.run_cycle()
    await poller.run_cycle()
    assert len(seventeen.calls) == 1
    assert (await repo.get_parcel(parcel.id)).state == "pending"
    assert notifier.sent == []


async def test_the_fallback_can_be_switched_off(env):
    repo, carrier, notifier, settings, no_sleep = env
    await add(repo, CODE, "cainiao")
    seventeen = FakeSeventeen()
    poller = build(
        repo, carrier, notifier, replace(settings, seventeen_fallback=False), no_sleep, seventeen
    )
    await poller.run_cycle()
    assert seventeen.calls == []


async def test_no_fallback_for_a_parcel_that_already_has_events(env):
    repo, carrier, notifier, settings, no_sleep = env
    from tests.fakes import ev, found

    parcel = await add(repo, CODE, "cainiao")
    carrier.results[(CODE, None)] = found("cainiao", CODE, ev(0, "Đã lấy hàng"))
    seventeen = FakeSeventeen()
    poller = build(repo, carrier, notifier, settings, no_sleep, seventeen)
    await poller.run_cycle()
    assert seventeen.calls == []
    assert await repo.count_events(parcel.id) == 1


async def test_a_registered_parcel_is_queried_again_for_free(env):
    repo, carrier, notifier, settings, no_sleep = env
    from tests.fakes import ev, found

    parcel = await add(repo, CODE, "cainiao")
    seventeen = FakeSeventeen()
    poller = build(repo, carrier, notifier, settings, no_sleep, seventeen)
    await poller.run_cycle()
    assert seventeen.calls == [(CODE, True)], "registers once"
    seventeen.result = found("cainiao", CODE, ev(0, "Đã đến Thượng Hải"))
    await poller.run_cycle(only_user_id=USER, wait=True)
    assert seventeen.calls[-1] == (CODE, False), "later polls are free queries"
    assert await repo.count_events(parcel.id) == 1
    assert (await repo.get_parcel(parcel.id)).state == "in_transit"


class BlockedSeventeen(FakeSeventeen):
    async def fetch(self, http, tracking_number, phone_last4=None, *, auto_register=True):
        from vn_parcel_bot.carriers.models import CarrierError

        self.calls.append((tracking_number, auto_register))
        raise CarrierError("cainiao", "blocked", "17track quota exceeded")


async def test_a_quota_error_leaves_the_parcel_for_another_day(env):
    repo, carrier, notifier, settings, no_sleep = env
    parcel = await add(repo, CODE, "cainiao")
    seventeen = BlockedSeventeen()
    poller = build(repo, carrier, notifier, settings, no_sleep, seventeen)
    await poller.run_cycle(only_user_id=USER, wait=True)
    assert await repo.get_meta(f"17track-tried:{parcel.id}") is None
    await poller.run_cycle(only_user_id=USER, wait=True)
    assert len(seventeen.calls) == 2, "a parcel is not written off because quota ran out"


def delivered_payload(description: str, location: str, sub_status: str = "") -> dict:
    return {
        "code": 0,
        "data": {
            "accepted": [
                {
                    "number": CODE,
                    "carrier": 190324,
                    "latest_status": {"status": "Delivered", "sub_status": sub_status},
                    "track_info": {
                        "tracking": {
                            "providers": [
                                {
                                    "events": [
                                        {
                                            "time_utc": "2026-09-16T01:26:08Z",
                                            "description": description,
                                            "location": location,
                                        }
                                    ]
                                }
                            ]
                        }
                    },
                }
            ],
            "rejected": [],
        },
    }


async def fetch_payload(payload: dict):
    respx.post(GET_TRACK_INFO_URL).mock(return_value=httpx.Response(200, json=payload))
    carrier = SeventeenTrackCarrier(
        carrier_code="cainiao", display_name="Cainiao", seventeen_carrier_id=None, api_key="k"
    )
    async with httpx.AsyncClient() as http:
        return await carrier.fetch(http, CODE)


@respx.mock
async def test_a_chinese_warehouse_signature_is_not_delivery_to_the_buyer():
    result = await fetch_payload(delivered_payload("您的快件已由【仓库】代收", "东莞市"))
    assert result.found is True
    assert result.delivered is False, "the origin leg ended, the buyer has nothing yet"


@respx.mock
async def test_a_locker_drop_is_not_delivery_to_the_buyer():
    result = await fetch_payload(delivered_payload("Đã giao vào locker toà nhà", "Hà Nội"))
    assert result.delivered is False


@respx.mock
async def test_delivery_to_the_buyer_still_counts():
    result = await fetch_payload(delivered_payload("Giao hàng thành công", "Hà Nội"))
    assert result.found is True
    assert result.delivered is True
