from dataclasses import replace
from datetime import UTC, datetime

import pytest

from tests.test_maps import blank_tile
from vn_parcel_bot import texts
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.maps import MapError
from vn_parcel_bot.services.parcel_maps import ParcelMaps

T0 = datetime(2026, 9, 15, 3, 0, tzinfo=UTC)
HUB = "21-HNI Thanh Tri 2 Hub"
HOME = (21.03, 105.85)


class FakeGeocoder:
    def __init__(self, point=(20.94, 105.84)):
        self.point = point
        self.calls = []

    async def coordinates(self, raw):
        self.calls.append(raw)
        return self.point


async def tiles(z, x, y):
    return blank_tile()


@pytest.fixture
async def env(tmp_path, settings):
    repo = await Repository.open(tmp_path / "bot.sqlite3")
    try:
        await repo.upsert_user(1, now=T0, is_allowed=True)
        parcel = await repo.add_parcel(
            user_id=1,
            carrier="spx",
            candidates=("spx",),
            tracking_number="SPXVN000000000001",
            phone_last4=None,
            now=T0,
            next_check_at=T0,
        )
        await repo.set_place(parcel.id, HUB)
        yield repo, settings, await repo.get_parcel(parcel.id)
    finally:
        await repo.close()


async def test_place_line_without_home_shows_only_the_hub(env):
    repo, settings, parcel = env
    maps = ParcelMaps(repo, FakeGeocoder(), tiles, settings)
    line = await maps.place_line(parcel, await repo.get_user(1))
    assert line == texts.PLACE_ONLY_LINE.format(place="Kho Thanh Tri")


async def test_place_line_uses_only_the_cache(env):
    repo, settings, parcel = env
    await repo.set_home(1, *HOME)
    geocoder = FakeGeocoder()
    maps = ParcelMaps(repo, geocoder, tiles, settings)
    user = await repo.get_user(1)
    assert await maps.place_line(parcel, user) == texts.PLACE_ONLY_LINE.format(
        place="Kho Thanh Tri"
    )
    await repo.save_place("HNI|Thanh Tri", 20.94, 105.84, "osm", T0)
    line = await maps.place_line(parcel, user)
    assert line == texts.PLACE_LINE.format(place="Kho Thanh Tri", distance="~10 km")
    assert geocoder.calls == []


async def test_place_line_escapes_the_hub_name(env):
    repo, settings, parcel = env
    await repo.set_place(parcel.id, "Bưu cục <Quận 7>")
    maps = ParcelMaps(repo, FakeGeocoder(), tiles, settings)
    line = await maps.place_line(await repo.get_parcel(parcel.id), await repo.get_user(1))
    assert line == texts.PLACE_ONLY_LINE.format(place="&lt;Quận 7&gt;")


async def test_photo_needs_home_and_place_and_renders(env):
    repo, settings, parcel = env
    maps = ParcelMaps(repo, FakeGeocoder(), tiles, settings)
    assert await maps.photo(parcel, await repo.get_user(1)) is None
    await repo.set_home(1, *HOME)
    user = await repo.get_user(1)
    png, caption = await maps.photo(parcel, user)
    assert png.startswith(b"\x89PNG")
    assert caption.startswith("🗺 <b>")
    assert "Kho Thanh Tri" in caption
    assert "~10 km" in caption
    assert await ParcelMaps(repo, FakeGeocoder(None), tiles, settings).photo(parcel, user) is None


async def test_photo_passes_render_failures_on(env):
    repo, settings, parcel = env
    await repo.set_home(1, *HOME)

    async def broken(z, x, y):
        raise MapError("tile")

    maps = ParcelMaps(repo, FakeGeocoder(), broken, settings)
    with pytest.raises(MapError):
        await maps.photo(parcel, await repo.get_user(1))


async def test_maps_disabled_gives_nothing(env):
    repo, settings, parcel = env
    await repo.set_home(1, *HOME)
    geocoder = FakeGeocoder()
    maps = ParcelMaps(repo, geocoder, tiles, replace(settings, maps_enabled=False))
    user = await repo.get_user(1)
    assert await maps.place_line(parcel, user) is None
    assert await maps.photo(parcel, user) is None
    assert geocoder.calls == []


async def test_prepare_looks_the_place_up_only_when_maps_are_on(env):
    repo, settings, _ = env
    geocoder = FakeGeocoder()
    await ParcelMaps(repo, geocoder, tiles, settings).prepare(HUB)
    assert geocoder.calls == [HUB]
    switched_off = FakeGeocoder()
    await ParcelMaps(repo, switched_off, tiles, replace(settings, maps_enabled=False)).prepare(HUB)
    assert switched_off.calls == []


class AreaGeocoder(FakeGeocoder):
    async def search_area(self, text):
        self.calls.append(text)
        return (21.0, 105.8), "Hà Nội"


async def test_find_area_asks_the_geocoder_only_when_maps_are_on(env):
    repo, settings, _ = env
    areas = AreaGeocoder()
    found = await ParcelMaps(repo, areas, tiles, settings).find_area("Hà Nội")
    assert found == ((21.0, 105.8), "Hà Nội")
    assert areas.calls == ["Hà Nội"]
    switched_off = AreaGeocoder()
    maps = ParcelMaps(repo, switched_off, tiles, replace(settings, maps_enabled=False))
    assert await maps.find_area("Hà Nội") is None
    assert switched_off.calls == []


async def test_list_places_gives_a_line_and_a_distance_for_each_parcel(env):
    repo, settings, parcel = env
    await repo.set_home(1, *HOME)
    await repo.save_place("HNI|Thanh Tri", 20.94, 105.84, "osm", T0)
    maps = ParcelMaps(repo, FakeGeocoder(), tiles, settings)
    lines, distances = await maps.list_places([parcel], await repo.get_user(1))
    assert lines[parcel.id] == texts.PLACE_LINE.format(place="Kho Thanh Tri", distance="~10 km")
    assert 9 < distances[parcel.id] < 11


async def test_list_places_leaves_out_a_parcel_with_no_hub(env):
    import dataclasses

    repo, settings, parcel = env
    maps = ParcelMaps(repo, FakeGeocoder(), tiles, settings)
    lines, distances = await maps.list_places(
        [dataclasses.replace(parcel, place=None)], await repo.get_user(1)
    )
    assert lines == {}
    assert distances == {}


async def test_ensure_prepared_looks_up_a_key_with_no_row_yet(env):
    repo, settings, _ = env
    geocoder = FakeGeocoder()
    maps = ParcelMaps(repo, geocoder, tiles, settings)

    await maps.ensure_prepared("21-HNI Thanh Tri 2 Hub")

    assert geocoder.calls == ["21-HNI Thanh Tri 2 Hub"]


async def test_ensure_prepared_leaves_a_looked_up_hub_alone(env):
    repo, settings, _ = env
    await repo.save_place("HNI|Thanh Tri", 20.94, 105.84, "osm", T0)
    geocoder = FakeGeocoder()
    maps = ParcelMaps(repo, geocoder, tiles, settings)

    await maps.ensure_prepared("21-HNI Thanh Tri 2 Hub")

    assert geocoder.calls == [], "a hub that has coordinates is never asked for twice"


async def test_list_places_shows_the_hub_alone_when_the_distance_is_unknown(env):
    repo, settings, parcel = env
    maps = ParcelMaps(repo, FakeGeocoder(), tiles, settings)
    lines, distances = await maps.list_places([parcel], await repo.get_user(1))
    assert lines[parcel.id] == texts.PLACE_ONLY_LINE.format(place="Kho Thanh Tri")
    assert distances == {}
