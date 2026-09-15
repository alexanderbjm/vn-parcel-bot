import io
import os
import time

import httpx
import pytest
import respx
from PIL import Image

from vn_parcel_bot.services.maps import (
    ATTRIBUTION,
    HEIGHT,
    MAX_ZOOM,
    MIN_ZOOM,
    TILE_URL,
    WIDTH,
    MapError,
    TileCache,
    choose_zoom,
    render_map,
)

HOME = (21.03, 105.85)


def blank_tile() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (256, 256), (230, 230, 230)).save(buffer, "PNG")
    return buffer.getvalue()


def test_tiles_come_from_carto_and_credit_both_sources():
    assert TILE_URL.startswith("https://a.basemaps.cartocdn.com/rastertiles/voyager/")
    assert "OpenStreetMap" in ATTRIBUTION
    assert "CARTO" in ATTRIBUTION


def test_zoom_is_closer_for_near_points():
    near = choose_zoom(HOME, (21.04, 105.86))
    far = choose_zoom(HOME, (10.78, 106.70))
    assert MIN_ZOOM <= far < near <= MAX_ZOOM


async def test_render_map_makes_a_600_by_400_png():
    calls = []

    async def tiles(z, x, y):
        calls.append((z, x, y))
        return blank_tile()

    png = await render_map(HOME, (20.94, 105.84), tiles)
    image = Image.open(io.BytesIO(png))
    assert (image.format, image.size) == ("PNG", (WIDTH, HEIGHT))
    assert calls
    assert all(0 <= y < 2**z and 0 <= x < 2**z for z, x, y in calls)


async def test_render_map_fails_when_a_tile_fails():
    async def tiles(z, x, y):
        raise MapError("tile")

    with pytest.raises(MapError):
        await render_map(HOME, (20.94, 105.84), tiles)


@respx.mock
async def test_tile_cache_downloads_once_and_refreshes_after_a_week(tmp_path):
    route = respx.get(TILE_URL.format(z=12, x=3257, y=1780)).mock(
        return_value=httpx.Response(200, content=b"png")
    )
    clock = [time.time()]
    async with httpx.AsyncClient() as http:
        cache = TileCache(http, tmp_path, now=lambda: clock[0])
        assert await cache.get(12, 3257, 1780) == b"png"
        assert await cache.get(12, 3257, 1780) == b"png"
        assert route.call_count == 1
        assert route.calls.last.request.headers["User-Agent"].startswith("vn-parcel-bot/")
        clock[0] += 8 * 24 * 3600
        await cache.get(12, 3257, 1780)
        assert route.call_count == 2


@respx.mock
async def test_tile_errors_become_map_errors(tmp_path):
    respx.get(TILE_URL.format(z=5, x=1, y=1)).mock(return_value=httpx.Response(503))
    async with httpx.AsyncClient() as http:
        with pytest.raises(MapError):
            await TileCache(http, tmp_path).get(5, 1, 1)
    assert not os.listdir(tmp_path)
