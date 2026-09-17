import asyncio
import logging
import math
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx

from vn_parcel_bot import texts
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.geo_provinces import PROVINCES

log = logging.getLogger(__name__)

_LEADING_NUMBER = re.compile(r"^\d{1,3}-")
_POST_OFFICE = re.compile(r"^bưu cục\s+", re.IGNORECASE)
_HUB_WORDS = frozenset({"hub", "soc", "mega", "lm", "kho", "bc"})
EARTH_RADIUS_KM = 6371.0

# openstreetmap.org is blocked from the bot's PC (2026-09-15), so places are looked up on Photon,
# which serves OpenStreetMap data.
PHOTON_URL = "https://photon.komoot.io/api/"
USER_AGENT = "vn-parcel-bot/0.1 (personal Telegram parcel tracker)"
VIETNAM_BBOX = "102.1,8.1,109.5,23.4"
# A hub on a parcel route to Vietnam sits in Vietnam or just over the border (a Chinese city).
# A short or ambiguous name ("BD") matched against the whole world lands anywhere at all — which
# is how a hub ended up 8358 km away — so a worldwide match beyond this counts as no match.
VIETNAM_CENTRE = (16.0, 106.0)
MAX_HUB_KM = 4000.0
# A hub abroad often shares its name with somewhere in Vietnam (Dongguan reads as the
# commune Đông Quan), so these are asked for by their own name and never matched at home.
FOREIGN_PLACES = {
    "Thượng Hải": "Shanghai, China",
    "Thâm Quyến": "Shenzhen, China",
    "Đông Quản": "Dongguan, China",
    "Quảng Châu": "Guangzhou, China",
    "Bắc Kinh": "Beijing, China",
    "Nam Ninh": "Nanning, China",
    "Côn Minh": "Kunming, China",
    "Nghĩa Ô": "Yiwu, China",
    "Hàng Châu": "Hangzhou, China",
    "Tuyền Châu": "Quanzhou, China",
    "Quảng Đông": "Guangdong, China",
    "Quảng Tây": "Guangxi, China",
    "Phúc Kiến": "Fujian, China",
    "Chiết Giang": "Zhejiang, China",
    "Vân Nam": "Yunnan, China",
    "Bằng Tường": "Pingxiang, Guangxi, China",
    "Hữu Nghị Quan": "Pingxiang, Guangxi, China",
    "Hồng Kông": "Hong Kong",
}
MISS_RETRY_AFTER = timedelta(days=30)
MIN_REQUEST_GAP_SECONDS = 1.1
AREA_NAME_KEYS = ("name", "district", "city", "county", "state")
LOOKUP_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class PlaceParts:
    code: str | None
    district: str | None

    @property
    def key(self) -> str:
        return f"{self.code or ''}|{self.district or ''}"

    @property
    def display(self) -> str | None:
        if self.code is not None:
            return f"Kho {self.district or PROVINCES[self.code][0]}"
        return self.district


def _is_hub_suffix(token: str) -> bool:
    return token.isdigit() or (len(token) == 1 and token.isalpha())


def clean_place(raw: str) -> PlaceParts:
    """Split hub text like "21-HNI Thanh Tri 2 Hub" into a province code and a district."""
    text = _POST_OFFICE.sub("", _LEADING_NUMBER.sub("", " ".join(raw.split())))
    tokens = text.split(" ") if text else []
    code = tokens.pop(0) if tokens and tokens[0] in PROVINCES else None
    dropped = False
    while tokens and tokens[-1].casefold() in _HUB_WORDS:
        tokens.pop()
        dropped = True
    while dropped and tokens and _is_hub_suffix(tokens[-1]):
        tokens.pop()
    return PlaceParts(code, " ".join(tokens) or None)


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def format_distance(km: float) -> str:
    if km < 1:
        return texts.DISTANCE_UNDER_1KM
    if km < 10:
        return f"~{km:.1f} km"
    return f"~{round(km)} km"


def plausible_hub(point: tuple[float, float]) -> bool:
    """True when a hub could plausibly sit on a parcel route into Vietnam."""
    return haversine_km(VIETNAM_CENTRE, point) <= MAX_HUB_KM


class AreaLookupFailed(Exception):
    """A written area could not be looked up (network or service error)."""


def _first_vietnam_feature(
    data: object, vietnam_only: bool = True
) -> tuple[tuple[float, float], dict] | None:
    features = data.get("features") if isinstance(data, dict) else None
    if not isinstance(features, list) or not features or not isinstance(features[0], dict):
        return None
    feature = features[0]
    properties = feature.get("properties")
    props = properties if isinstance(properties, dict) else {}
    if vietnam_only and props.get("countrycode") not in (None, "VN"):
        return None
    try:
        lon, lat = feature["geometry"]["coordinates"][:2]
        return (float(lat), float(lon)), props
    except (KeyError, TypeError, ValueError):
        return None


def _area_name(props: dict, fallback: str) -> str:
    parts = (props.get(key) for key in AREA_NAME_KEYS)
    names = dict.fromkeys(" ".join(part.split()) for part in parts if isinstance(part, str))
    return ", ".join(name for name in names if name) or fallback


class Geocoder:
    """Coordinates for hub text: cached Photon lookups, province centres as a fallback."""

    def __init__(
        self,
        repo: Repository,
        http: httpx.AsyncClient,
        now: Callable[[], datetime],
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._repo = repo
        self._http = http
        self._now = now
        self._sleep = sleep
        self._monotonic = monotonic
        self._lock = asyncio.Lock()
        self._last_request: float | None = None

    async def coordinates(self, raw_place: str) -> tuple[float, float] | None:
        parts = clean_place(raw_place)
        if parts.code is None and parts.district is None:
            return None
        now = self._now()
        cached = await self._repo.get_place(parts.key)
        if cached is not None:
            if cached.lat is not None and cached.lon is not None:
                if plausible_hub((cached.lat, cached.lon)):
                    return cached.lat, cached.lon
                # A row an earlier release wrote from an unbounded match: resolve it again rather
                # than keep drawing the hub on the far side of the world.
                log.info("implausible cached hub key=%s", parts.key)
            elif now - cached.looked_up_at < MISS_RETRY_AFTER:
                return None
        province = PROVINCES.get(parts.code) if parts.code is not None else None
        centre = (province[1], province[2]) if province is not None else None
        if parts.district is not None:
            query = f"{parts.district}, {province[0]}" if province is not None else parts.district
            try:
                point = await self._search(query)
            except (httpx.HTTPError, ValueError) as exc:
                log.warning("place lookup failed type=%s", type(exc).__name__)
                return centre
            if point is not None:
                await self._repo.save_place(parts.key, point[0], point[1], "osm", now)
                return point
        if centre is not None:
            await self._repo.save_place(parts.key, centre[0], centre[1], "province", now)
            return centre
        await self._repo.save_place(parts.key, None, None, "none", now)
        return None

    async def search_area(self, text: str) -> tuple[tuple[float, float], str] | None:
        """A written area's coordinates and readable name; not cached, the text is never logged."""
        query = " ".join(text.split())
        try:
            found = await self._lookup(query)
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("area lookup failed type=%s", type(exc).__name__)
            raise AreaLookupFailed(type(exc).__name__) from exc
        if found is None:
            return None
        point, props = found
        return point, _area_name(props, query)

    async def _search(self, query: str) -> tuple[float, float] | None:
        abroad = FOREIGN_PLACES.get(query)
        if abroad is not None:
            found = await self._lookup(abroad, worldwide=True)
            return found[0] if found is not None else None
        found = await self._lookup(query)
        if found is None:
            # A hub on a cross-border parcel sits outside Vietnam (a Chinese city, say), so a
            # second pass drops the bounding box — but only a match near enough to be on the
            # route counts, so an unbounded hit on a short name cannot become a hub.
            worldwide = await self._lookup(query, worldwide=True)
            found = worldwide if worldwide is not None and plausible_hub(worldwide[0]) else None
        return found[0] if found is not None else None

    async def _lookup(
        self, query: str, worldwide: bool = False
    ) -> tuple[tuple[float, float], dict] | None:
        async with self._lock:
            if self._last_request is not None:
                wait = MIN_REQUEST_GAP_SECONDS - (self._monotonic() - self._last_request)
                if wait > 0:
                    await self._sleep(wait)
            try:
                response = await self._http.get(
                    PHOTON_URL,
                    params=(
                        {"q": query, "limit": 1}
                        if worldwide
                        else {"q": query, "limit": 1, "bbox": VIETNAM_BBOX}
                    ),
                    headers={"User-Agent": USER_AGENT},
                    timeout=LOOKUP_TIMEOUT_SECONDS,
                )
            finally:
                self._last_request = self._monotonic()
        response.raise_for_status()
        return _first_vietnam_feature(response.json(), vietnam_only=not worldwide)
