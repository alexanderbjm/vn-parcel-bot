"""Map picture with the user's area, the hub pin and a dashed line between them."""

import asyncio
import io
import math
import time
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

from vn_parcel_bot.services.geo import USER_AGENT

# openstreetmap.org is blocked from the bot's PC (2026-09-15), so the squares come from CARTO's
# Voyager style, which draws OpenStreetMap data.
TILE_URL = "https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png"
ATTRIBUTION = "© OpenStreetMap contributors © CARTO"
TILE_SIZE = 256
WIDTH, HEIGHT = 600, 400
MIN_ZOOM, MAX_ZOOM = 5, 15
MARGIN = 40
AREA_RADIUS_M = 1000
TILE_MAX_AGE_SECONDS = 7 * 24 * 3600
TILE_TIMEOUT_SECONDS = 15
METRES_PER_PIXEL_AT_ZOOM_0 = 156543.03392

TileSource = Callable[[int, int, int], Awaitable[bytes]]
Point = tuple[float, float]


class MapError(Exception):
    pass


def world_px(point: Point, zoom: int) -> Point:
    lat, lon = point
    scale = TILE_SIZE * 2**zoom
    sin = math.sin(math.radians(lat))
    y = 0.5 - math.log((1 + sin) / (1 - sin)) / (4 * math.pi)
    return (lon + 180) / 360 * scale, y * scale


def area_radius_px(lat: float, zoom: int) -> float:
    return AREA_RADIUS_M / (METRES_PER_PIXEL_AT_ZOOM_0 * math.cos(math.radians(lat)) / 2**zoom)


def choose_zoom(home: Point, place: Point) -> int:
    """The closest zoom at which both points, the user's area and a margin fit the picture."""
    for zoom in range(MAX_ZOOM, MIN_ZOOM - 1, -1):
        (hx, hy), (px, py) = world_px(home, zoom), world_px(place, zoom)
        pad = 2 * (area_radius_px(home[0], zoom) + MARGIN)
        if abs(hx - px) + pad <= WIDTH and abs(hy - py) + pad <= HEIGHT:
            return zoom
    return MIN_ZOOM


class TileCache:
    """Map squares on disk under `directory/z/x/y.png`, downloaded again after a week."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        directory: Path,
        now: Callable[[], float] = time.time,
        max_parallel: int = 2,
    ) -> None:
        self._http = http
        self._directory = directory
        self._now = now
        self._semaphore = asyncio.Semaphore(max_parallel)

    def _fresh(self, path: Path) -> bytes | None:
        if path.is_file() and self._now() - path.stat().st_mtime < TILE_MAX_AGE_SECONDS:
            return path.read_bytes()
        return None

    @staticmethod
    def _store(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def get(self, z: int, x: int, y: int) -> bytes:
        path = self._directory / str(z) / str(x) / f"{y}.png"
        cached = await asyncio.to_thread(self._fresh, path)
        if cached is not None:
            return cached
        async with self._semaphore:
            try:
                response = await self._http.get(
                    TILE_URL.format(z=z, x=x, y=y),
                    headers={"User-Agent": USER_AGENT},
                    timeout=TILE_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise MapError(type(exc).__name__) from exc
        await asyncio.to_thread(self._store, path, response.content)
        return response.content


async def render_map(home: Point, place: Point, tiles: TileSource) -> bytes:
    """A 600×400 PNG centred between the user's area and the hub."""
    zoom = choose_zoom(home, place)
    (hx, hy), (px, py) = world_px(home, zoom), world_px(place, zoom)
    left, top = (hx + px) / 2 - WIDTH / 2, (hy + py) / 2 - HEIGHT / 2
    count = 2**zoom
    first_x, last_x = math.floor(left / TILE_SIZE), math.floor((left + WIDTH - 1) / TILE_SIZE)
    first_y, last_y = math.floor(top / TILE_SIZE), math.floor((top + HEIGHT - 1) / TILE_SIZE)
    coords = [
        (x, y)
        for x in range(first_x, last_x + 1)
        for y in range(first_y, last_y + 1)
        if 0 <= y < count
    ]
    images = await asyncio.gather(*(tiles(zoom, x % count, y) for x, y in coords))
    radius = max(6.0, area_radius_px(home[0], zoom))
    return await asyncio.to_thread(
        _compose, coords, images, left, top, (hx - left, hy - top), (px - left, py - top), radius
    )


def _compose(
    coords: Sequence[tuple[int, int]],
    images: Sequence[bytes],
    left: float,
    top: float,
    home_xy: Point,
    place_xy: Point,
    radius: float,
) -> bytes:
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), "white")
    for (x, y), data in zip(coords, images, strict=True):
        try:
            tile = Image.open(io.BytesIO(data)).convert("RGBA")
        except (OSError, ValueError) as exc:
            raise MapError(type(exc).__name__) from exc
        canvas.paste(tile, (round(x * TILE_SIZE - left), round(y * TILE_SIZE - top)))
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    (hx, hy), (px, py) = home_xy, place_xy
    steps = max(1, int(math.hypot(px - hx, py - hy) // 12))
    for i in range(0, steps, 2):
        a, b = i / steps, min(1.0, (i + 1) / steps)
        draw.line(
            (hx + (px - hx) * a, hy + (py - hy) * a, hx + (px - hx) * b, hy + (py - hy) * b),
            fill=(40, 40, 40, 220),
            width=3,
        )
    draw.ellipse(
        (hx - radius, hy - radius, hx + radius, hy + radius),
        fill=(30, 120, 255, 70),
        outline=(30, 120, 255, 255),
        width=3,
    )
    draw.polygon(((px, py), (px - 9, py - 16), (px + 9, py - 16)), fill=(220, 40, 40, 255))
    draw.ellipse(
        (px - 10, py - 30, px + 10, py - 10), fill=(220, 40, 40, 255), outline="white", width=2
    )
    font = ImageFont.load_default(size=12)
    text_box = draw.textbbox((0, 0), ATTRIBUTION, font=font)
    box_width, box_height = text_box[2] + 8, text_box[3] + 6
    draw.rectangle(
        (WIDTH - box_width, HEIGHT - box_height, WIDTH, HEIGHT), fill=(255, 255, 255, 220)
    )
    draw.text(
        (WIDTH - box_width + 4, HEIGHT - box_height + 3),
        ATTRIBUTION,
        font=font,
        fill=(60, 60, 60, 255),
    )
    buffer = io.BytesIO()
    Image.alpha_composite(canvas, overlay).convert("RGB").save(buffer, "PNG")
    return buffer.getvalue()
