from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from tests.fakes import FakeClock
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.geo import (
    PHOTON_URL,
    USER_AGENT,
    VIETNAM_BBOX,
    AreaLookupFailed,
    Geocoder,
)
from vn_parcel_bot.services.geo_provinces import PROVINCES

T0 = datetime(2026, 9, 15, 3, 0, tzinfo=UTC)
MISS = {"type": "FeatureCollection", "features": []}


def hit(lat: float, lon: float, countrycode: str = "VN") -> httpx.Response:
    feature = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {"countrycode": countrycode, "name": "Huyện Mẫu"},
    }
    return httpx.Response(200, json={"type": "FeatureCollection", "features": [feature]})


@pytest.fixture
async def env(tmp_path):
    repo = await Repository.open(tmp_path / "bot.sqlite3")
    clock = FakeClock(T0)
    sleeps: list[float] = []
    ticks = iter(float(n) for n in range(1000))

    async def sleep(seconds):
        sleeps.append(seconds)

    http = httpx.AsyncClient()
    geocoder = Geocoder(repo, http, clock, sleep=sleep, monotonic=lambda: next(ticks) * 0.1)
    yield geocoder, repo, clock, sleeps
    await http.aclose()
    await repo.close()


@respx.mock
async def test_district_found_on_photon_is_cached(env):
    geocoder, repo, _, _ = env
    route = respx.get(PHOTON_URL).mock(return_value=hit(20.94, 105.84))
    assert await geocoder.coordinates("21-HNI Thanh Tri 2 Hub") == (20.94, 105.84)
    assert await geocoder.coordinates("21-HNI Thanh Tri 3 Hub") == (20.94, 105.84)
    assert route.call_count == 1
    request = route.calls.last.request
    assert request.headers["User-Agent"] == USER_AGENT
    assert request.url.params["q"] == f"Thanh Tri, {PROVINCES['HNI'][0]}"
    assert request.url.params["limit"] == "1"
    assert request.url.params["bbox"] == VIETNAM_BBOX
    assert (await repo.get_place("HNI|Thanh Tri")).source == "osm"


@respx.mock
async def test_province_centre_when_the_district_is_unknown(env):
    geocoder, repo, _, _ = env
    respx.get(PHOTON_URL).mock(return_value=httpx.Response(200, json=MISS))
    _, lat, lon = PROVINCES["HPG"]
    assert await geocoder.coordinates("24-HPG Nowhere Hub") == (lat, lon)
    assert (await repo.get_place("HPG|Nowhere")).source == "province"


@respx.mock
async def test_a_hit_outside_vietnam_counts_as_a_miss(env):
    geocoder, repo, _, _ = env
    respx.get(PHOTON_URL).mock(return_value=hit(48.1, 11.5, countrycode="DE"))
    assert await geocoder.coordinates("Bưu cục Somewhere") is None
    assert (await repo.get_place("|Somewhere")).source == "none"


@respx.mock
async def test_province_only_hub_needs_no_request(env):
    geocoder, _, _, _ = env
    route = respx.get(PHOTON_URL)
    _, lat, lon = PROVINCES["BN"]
    assert await geocoder.coordinates("BN B Mega SOC") == (lat, lon)
    assert not route.called


@respx.mock
async def test_misses_are_cached_for_30_days(env):
    geocoder, _, clock, _ = env
    route = respx.get(PHOTON_URL).mock(return_value=httpx.Response(200, json=MISS))
    assert await geocoder.coordinates("Bưu cục Không Có") is None
    assert await geocoder.coordinates("Bưu cục Không Có") is None
    assert route.call_count == 1
    clock.advance(timedelta(days=31))
    assert await geocoder.coordinates("Bưu cục Không Có") is None
    assert route.call_count == 2


@pytest.mark.parametrize(
    "outcome",
    [httpx.Response(503), httpx.ConnectError("reset"), httpx.Response(200, text="not json")],
    ids=["status", "network", "garbage"],
)
@respx.mock
async def test_errors_are_not_cached(env, outcome):
    geocoder, repo, _, _ = env
    if isinstance(outcome, Exception):
        respx.get(PHOTON_URL).mock(side_effect=outcome)
    else:
        respx.get(PHOTON_URL).mock(return_value=outcome)
    assert await geocoder.coordinates("Bưu cục Quận 7") is None
    assert await repo.get_place("|Quận 7") is None


@respx.mock
async def test_errors_on_a_province_hub_fall_back_to_the_province_without_caching(env):
    geocoder, repo, _, _ = env
    respx.get(PHOTON_URL).mock(side_effect=httpx.ConnectError("reset"))
    _, lat, lon = PROVINCES["HNI"]
    assert await geocoder.coordinates("21-HNI Thanh Tri 2 Hub") == (lat, lon)
    assert await repo.get_place("HNI|Thanh Tri") is None


@respx.mock
async def test_requests_are_spaced(env):
    geocoder, _, _, sleeps = env
    respx.get(PHOTON_URL).mock(return_value=hit(10.0, 106.0))
    await geocoder.coordinates("Bưu cục A1")
    await geocoder.coordinates("Bưu cục A2")
    assert len(sleeps) == 1
    assert 0.9 < sleeps[0] <= 1.1


@respx.mock
async def test_written_area_returns_the_point_and_a_readable_name(env):
    geocoder, repo, _, _ = env
    feature = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [105.7906, 21.0362]},
        "properties": {
            "countrycode": "VN",
            "name": "Dịch Vọng",
            "district": "Cầu Giấy",
            "city": "Hà Nội",
            "state": "Hà Nội",
        },
    }
    route = respx.get(PHOTON_URL).mock(
        return_value=httpx.Response(200, json={"type": "FeatureCollection", "features": [feature]})
    )
    found = await geocoder.search_area("  Dịch Vọng,  Cầu Giấy ")
    assert found == ((21.0362, 105.7906), "Dịch Vọng, Cầu Giấy, Hà Nội")
    request = route.calls.last.request
    assert request.url.params["q"] == "Dịch Vọng, Cầu Giấy"
    assert request.url.params["bbox"] == VIETNAM_BBOX
    assert request.headers["User-Agent"] == USER_AGENT
    assert await repo.get_place("|Dịch Vọng, Cầu Giấy") is None


@respx.mock
async def test_written_area_outside_vietnam_or_unknown_is_none(env):
    geocoder, _, _, _ = env
    respx.get(PHOTON_URL).mock(
        side_effect=[hit(48.1, 11.5, countrycode="DE"), httpx.Response(200, json=MISS)]
    )
    assert await geocoder.search_area("München") is None
    assert await geocoder.search_area("Nowhere") is None


@respx.mock
async def test_written_area_errors_raise_without_logging_the_text(env, caplog):
    geocoder, _, _, _ = env
    respx.get(PHOTON_URL).mock(side_effect=httpx.ConnectError("reset"))
    with pytest.raises(AreaLookupFailed):
        await geocoder.search_area("Cầu Giấy")
    assert "area lookup failed type=ConnectError" in caplog.text
    assert "Cầu Giấy" not in caplog.text
