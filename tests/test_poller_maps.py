import logging
from datetime import UTC, datetime, timedelta

import pytest

from tests.fakes import FakeCarrier, FakeClock, FakeNotifier, fake_registry, found
from tests.test_maps import blank_tile
from tests.test_parcel_maps import FakeGeocoder
from vn_parcel_bot import texts
from vn_parcel_bot.carriers.models import TrackingEvent
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.geo import clean_place
from vn_parcel_bot.services.maps import MapError
from vn_parcel_bot.services.parcel_maps import ParcelMaps
from vn_parcel_bot.services.poller import Poller

T0 = datetime(2026, 9, 15, 3, 0, tzinfo=UTC)
SPX = "SPXVN000000000001"
HUB = "21-HNI Thanh Tri 2 Hub"


class SavingGeocoder(FakeGeocoder):
    """Like the real geocoder, a lookup fills the places cache that place lines read."""

    def __init__(self, repo):
        super().__init__()
        self.repo = repo

    async def coordinates(self, raw):
        point = await super().coordinates(raw)
        await self.repo.save_place(clean_place(raw).key, point[0], point[1], "osm", T0)
        return point


def hub(minutes, name=HUB):
    return TrackingEvent(
        time=T0 + timedelta(minutes=minutes), description=f"Đơn hàng đã đến kho {name}"
    )


async def tiles(z, x, y):
    return blank_tile()


async def no_sleep(seconds):
    return None


@pytest.fixture
async def env(tmp_path, settings):
    repo = await Repository.open(tmp_path / "bot.sqlite3")
    try:
        await repo.upsert_user(1, now=T0, is_allowed=True)
        carrier = FakeCarrier("spx")
        clock = FakeClock(T0)
        notifier = FakeNotifier()
        geocoder = SavingGeocoder(repo)
        maps = ParcelMaps(repo, geocoder, tiles, settings)
        poller = Poller(
            repo,
            fake_registry({"spx": carrier}),
            None,
            notifier,
            settings,
            clock,
            no_sleep,
            lambda: 0.0,
            maps=maps,
        )
        parcel = await repo.add_parcel(
            user_id=1,
            carrier="spx",
            candidates=("spx",),
            tracking_number=SPX,
            phone_last4=None,
            now=T0,
            next_check_at=T0,
        )
        yield poller, repo, carrier, clock, notifier, maps, geocoder, parcel
    finally:
        await repo.close()


async def test_new_hub_sends_the_update_then_the_map(env):
    poller, repo, carrier, _, notifier, _, geocoder, parcel = env
    await repo.set_home(1, 21.03, 105.85)
    carrier.results[(SPX, None)] = found("spx", SPX, hub(0))
    await poller.run_cycle()
    assert (await repo.get_parcel(parcel.id)).place == HUB
    # The lookup, then the map (a cache hit for the real geocoder).
    assert geocoder.calls == [HUB, HUB]
    text = notifier.sent[-1][1]
    assert text.endswith(texts.PLACE_LINE.format(place="Kho Thanh Tri", distance="~10 km"))
    markup = notifier.markups[-1]
    assert f"p:{parcel.id}:map" in [b.callback_data for row in markup.inline_keyboard for b in row]
    assert len(notifier.photos) == 1
    chat_id, png, caption, silent = notifier.photos[0]
    assert (chat_id, silent) == (1, True)
    assert png.startswith(b"\x89PNG")
    assert "Kho Thanh Tri" in caption


async def test_same_hub_is_not_mapped_twice(env):
    poller, repo, carrier, clock, notifier, _, geocoder, _ = env
    await repo.set_home(1, 21.03, 105.85)
    carrier.results[(SPX, None)] = found("spx", SPX, hub(0))
    await poller.run_cycle()
    carrier.results[(SPX, None)] = found(
        "spx",
        SPX,
        hub(0),
        TrackingEvent(time=T0 + timedelta(minutes=5), description="Đang giao hàng"),
    )
    clock.advance(timedelta(minutes=30))
    await poller.run_cycle()
    assert len(notifier.sent) == 2
    assert len(notifier.photos) == 1
    # The lookup, then the map (a cache hit for the real geocoder).
    assert geocoder.calls == [HUB, HUB]


async def test_without_home_the_place_is_kept_and_no_map_is_sent(env):
    poller, repo, carrier, _, notifier, _, _, parcel = env
    carrier.results[(SPX, None)] = found("spx", SPX, hub(0))
    await poller.run_cycle()
    assert (await repo.get_parcel(parcel.id)).place == HUB
    assert notifier.sent[-1][1].endswith(texts.PLACE_ONLY_LINE.format(place="Kho Thanh Tri"))
    assert notifier.photos == []


async def test_map_failure_still_sends_the_update(env, monkeypatch, caplog):
    poller, repo, carrier, _, notifier, maps, _, _ = env
    caplog.set_level(logging.WARNING)
    await repo.set_home(1, 21.03, 105.85)

    async def broken(*args, **kwargs):
        raise MapError("tile")

    monkeypatch.setattr(maps, "photo", broken)
    carrier.results[(SPX, None)] = found("spx", SPX, hub(0))
    await poller.run_cycle()
    assert len(notifier.sent) == 1
    assert notifier.photos == []
    assert "map failed type=MapError" in caplog.text


async def test_poller_without_maps_sends_plain_updates(env, settings):
    _, repo, carrier, clock, notifier, _, _, parcel = env
    plain = Poller(
        repo,
        fake_registry({"spx": carrier}),
        None,
        notifier,
        settings,
        clock,
        no_sleep,
        lambda: 0.0,
    )
    carrier.results[(SPX, None)] = found("spx", SPX, hub(0))
    await plain.run_cycle()
    assert "📍" not in notifier.sent[-1][1]
    assert (await repo.get_parcel(parcel.id)).place is None
    assert notifier.photos == []
