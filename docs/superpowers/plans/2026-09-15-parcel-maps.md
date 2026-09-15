# Parcel Maps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show how far a parcel's current hub is from the user's coarse home area: a distance line on cards and updates, and an OpenStreetMap picture sent after hub changes and from a card button.

**Architecture:** Schema v4 stores a rounded home location per user, the latest hub text per parcel and a `places` cache. Carrier modules expose a `place(event)` hook; `services/geo.py` cleans hub text, looks it up (province table, then Nominatim) and measures distance; `services/maps.py` draws the picture from cached OSM tiles with Pillow; `services/parcel_maps.py` joins them for handlers and the poller.

**Tech Stack:** Python 3.13, python-telegram-bot 22.8, aiosqlite, httpx, Pillow ≥ 11 (new), pytest + respx.

**Spec:** `docs/superpowers/specs/2026-09-15-parcel-maps-design.md`

## Global Constraints

- Home coordinates are stored as `round(value, 2)`; they are never logged, never sent to Nominatim and never shown as numbers.
- Nominatim: `https://nominatim.openstreetmap.org/search`, params `q`, `countrycodes=vn`, `format=jsonv2`, `limit=1`, `accept-language=vi`; header `User-Agent: vn-parcel-bot/0.1 (personal Telegram parcel tracker)`; timeout 10 s; at least 1.1 s between requests; HTTP errors are not cached; misses (`source='none'`) are retried after 30 days.
- Tiles: `https://tile.openstreetmap.org/{z}/{x}/{y}.png`, same User-Agent, at most 2 concurrent downloads, cached in `data/tiles/{z}/{x}/{y}.png` for 7 days; the picture always shows `© OpenStreetMap contributors`.
- Picture: PNG 600×400, zoom 5..15, user area as a 1 km circle, 40 px margin.
- `MAPS_ENABLED` (default `true`) turns off place lines, map buttons, automatic maps and lookups.
- Callback data stays under 64 bytes and never contains a tracking code.
- No network in tests (respx or fakes); no real tracking codes in tests.
- `parcels.place` holds the raw hub text returned by the module's `place` hook; cleaning happens on use (deviation from spec §3 wording, same behaviour).
- Changing `carriers/api.py` needs a bot restart before a module file using `place=` is saved: stop the "VN Parcel Bot" task before Task 5 edits `spx.py`, start it again at the end of Task 10.
- Gates per task: task tests, `ruff check <files> --fix`, `ruff format <files>`; at the end `ruff check .`, `ruff format --check .`, full `pytest -q`.
- Commits end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01JNknSSDZMR9Cg8iyhqGxQN`.

## File Structure

| File | Responsibility |
|---|---|
| `src/vn_parcel_bot/db/schema.py` | migration 4 |
| `src/vn_parcel_bot/db/repo.py` | `User.home_*`, `Parcel.place`, `PlaceRow`, home/place/places methods |
| `src/vn_parcel_bot/services/geo_provinces.py` (new) | `PROVINCES` code → (name, lat, lon) |
| `src/vn_parcel_bot/services/geo.py` (new) | `PlaceParts`, `clean_place`, `haversine_km`, `format_distance`, `Geocoder` |
| `src/vn_parcel_bot/services/maps.py` (new) | tile math, `TileCache`, `render_map`, `MapError` |
| `src/vn_parcel_bot/services/parcel_maps.py` (new) | `ParcelMaps`: place line and map bytes for a parcel and user |
| `src/vn_parcel_bot/carriers/api.py`, `carriers/registry.py`, `carriers/modules/spx.py` | `place` hook |
| `src/vn_parcel_bot/bot/notifier.py`, `tests/fakes.py` | `send_photo` |
| `src/vn_parcel_bot/config.py`, `bot/deps.py`, `bot/app.py`, `bot/commands.py` | setting, wiring, `/location` |
| `src/vn_parcel_bot/keyboards.py`, `bot/handlers_user.py`, `bot/handlers_callback.py`, `texts.py`, `services/formatting.py` | location flow, map button, place line |
| `src/vn_parcel_bot/services/poller.py` | place tracking, automatic map |
| `pyproject.toml`, `BUILD_PLAN.md`, `SPEC.md`, `README.md`, `.env.example` | dependency and docs |

---

### Task 1: Schema v4 and repository

**Files:**
- Modify: `src/vn_parcel_bot/db/schema.py`, `src/vn_parcel_bot/db/repo.py`
- Test: `tests/test_repo_places.py` (new)

**Interfaces:**
- Produces: `User.home_lat: float | None`, `User.home_lon: float | None`, `Parcel.place: str | None`; `@dataclass(frozen=True) class PlaceRow(name: str, lat: float | None, lon: float | None, source: str, looked_up_at: datetime)`; `Repository.set_home(telegram_id: int, lat: float, lon: float) -> None`, `clear_home(telegram_id: int) -> None`, `set_place(parcel_id: int, place: str) -> None`, `get_place(name: str) -> PlaceRow | None`, `save_place(name: str, lat: float | None, lon: float | None, source: str, now: datetime) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
from datetime import UTC, datetime, timedelta

import aiosqlite

from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.db.schema import MIGRATIONS, SCHEMA_VERSION

T0 = datetime(2026, 9, 15, 3, 0, tzinfo=UTC)


async def test_home_location_is_rounded_and_cleared(tmp_path):
    repo = await Repository.open(tmp_path / "bot.sqlite3")
    await repo.upsert_user(1, now=T0, is_allowed=True)
    await repo.set_home(1, 21.02851, 105.85422)
    user = await repo.get_user(1)
    assert (user.home_lat, user.home_lon) == (21.03, 105.85)
    await repo.clear_home(1)
    user = await repo.get_user(1)
    assert (user.home_lat, user.home_lon) == (None, None)
    await repo.close()


async def test_parcel_place_and_places_cache(tmp_path):
    repo = await Repository.open(tmp_path / "bot.sqlite3")
    await repo.upsert_user(1, now=T0, is_allowed=True)
    parcel = await repo.add_parcel(
        user_id=1, carrier="spx", candidates=("spx",), tracking_number="SPXVN000000000001",
        phone_last4=None, now=T0, next_check_at=T0,
    )
    assert parcel.place is None
    await repo.set_place(parcel.id, "21-HNI Thanh Tri 2 Hub")
    assert (await repo.get_parcel(parcel.id)).place == "21-HNI Thanh Tri 2 Hub"
    assert await repo.get_place("HNI|Thanh Tri") is None
    await repo.save_place("HNI|Thanh Tri", 20.94, 105.84, "osm", T0)
    await repo.save_place("HNI|Thanh Tri", None, None, "none", T0 + timedelta(days=1))
    row = await repo.get_place("HNI|Thanh Tri")
    assert (row.lat, row.lon, row.source, row.looked_up_at) == (None, None, "none", T0 + timedelta(days=1))
    await repo.close()


async def test_migration_from_v3_keeps_rows_and_writes_a_backup(tmp_path):
    path = tmp_path / "bot.sqlite3"
    async with aiosqlite.connect(path) as conn:
        for script in MIGRATIONS[:3]:
            await conn.executescript(script)
        await conn.execute("PRAGMA user_version = 3")
        await conn.execute(
            "INSERT INTO users (telegram_id, is_allowed, created_at) VALUES (1, 1, ?)",
            (T0.isoformat(),),
        )
        await conn.commit()
    repo = await Repository.open(path)
    assert SCHEMA_VERSION == 4
    assert (await repo.get_user(1)).home_lat is None
    assert path.with_name("bot.sqlite3.bak-v3").exists()
    await repo.close()
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_repo_places.py -q -p no:cacheprovider`
Expected: FAIL (`AttributeError: 'Repository' object has no attribute 'set_home'`, `SCHEMA_VERSION == 3`).

- [ ] **Step 3: Implement**

`schema.py`: set `SCHEMA_VERSION = 4` and append to `MIGRATIONS`:

```python
    """
ALTER TABLE users ADD COLUMN home_lat REAL;
ALTER TABLE users ADD COLUMN home_lon REAL;
ALTER TABLE parcels ADD COLUMN place TEXT;
CREATE TABLE places (
  name TEXT PRIMARY KEY,
  lat REAL,
  lon REAL,
  source TEXT NOT NULL CHECK (source IN ('osm', 'province', 'none')),
  looked_up_at TEXT NOT NULL
);
""",
```

`repo.py`:
- `_PARCEL_COLUMNS` ends with `"created_at, updated_at, progress, place"`; `_USER_COLUMNS = "telegram_id, name, default_phone_last4, is_admin, is_allowed, created_at, home_lat, home_lon"`.
- `User` gains `home_lat: float | None = None` and `home_lon: float | None = None`; `_user` passes `home_lat=row["home_lat"], home_lon=row["home_lon"]`. `Parcel` gains `place: str | None = None` after `progress`; `_parcel` passes `place=row["place"]`.
- Add after `set_default_phone`:

```python
    async def set_home(self, telegram_id: int, lat: float, lon: float) -> None:
        await self._write(
            "UPDATE users SET home_lat = ?, home_lon = ? WHERE telegram_id = ?",
            (round(lat, 2), round(lon, 2), telegram_id),
        )

    async def clear_home(self, telegram_id: int) -> None:
        await self._write(
            "UPDATE users SET home_lat = NULL, home_lon = NULL WHERE telegram_id = ?",
            (telegram_id,),
        )
```

- Add after `set_label`:

```python
    async def set_place(self, parcel_id: int, place: str) -> None:
        await self._write("UPDATE parcels SET place = ? WHERE id = ?", (place, parcel_id))
```

- Add a `PlaceRow` dataclass next to `User` and, in a `# places` section before `# meta`:

```python
    async def get_place(self, name: str) -> PlaceRow | None:
        row = await self._fetchone(
            "SELECT name, lat, lon, source, looked_up_at FROM places WHERE name = ?", (name,)
        )
        if row is None:
            return None
        return PlaceRow(row["name"], row["lat"], row["lon"], row["source"], _required(row["looked_up_at"]))

    async def save_place(
        self, name: str, lat: float | None, lon: float | None, source: str, now: datetime
    ) -> None:
        await self._write(
            "INSERT INTO places (name, lat, lon, source, looked_up_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET lat = excluded.lat, lon = excluded.lon, "
            "source = excluded.source, looked_up_at = excluded.looked_up_at",
            (name, lat, lon, source, _to_db(now)),
        )
```

- [ ] **Step 4: Run tests** — `pytest tests/test_repo_places.py tests/test_repo.py -q` → PASS (update any `test_repo.py` assertion that pins `SCHEMA_VERSION == 3` to 4).
- [ ] **Step 5: Commit** — `git add src/vn_parcel_bot/db tests/test_repo_places.py tests/test_repo.py` and commit "Schema v4: home location, parcel place and places cache".

---

### Task 2: Place cleaning, distance and the province table

**Files:**
- Create: `src/vn_parcel_bot/services/geo_provinces.py`, `src/vn_parcel_bot/services/geo.py`
- Test: `tests/test_geo.py` (new)

**Interfaces:**
- Produces: `PROVINCES: dict[str, tuple[str, float, float]]`; `@dataclass(frozen=True) class PlaceParts(code: str | None, district: str | None)` with property `key -> str` (`f"{code or ''}|{district or ''}"`) and `display -> str | None`; `clean_place(raw: str) -> PlaceParts`; `haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float`; `format_distance(km: float) -> str`.

- [ ] **Step 1: Draft the province table with agy (text only, no tools)**

Run in PowerShell (this matches the existing Claude Code allow rule):

```powershell
agy --mode plan --sandbox --model gemini-3.8-flash-medium --output-format text -p="List the 2-3 letter province codes Vietnamese parcel carriers (Shopee Xpress hubs such as 21-HNI, 24-HPG, 11-TQG, 10-VPC, BN A Mega SOC) use for all 63 pre-2025 provinces. Reply ONLY with Python dict lines in this exact form, one per province: 'HNI': ('Hà Nội', 21.0285, 105.8542), using the provincial capital's latitude and longitude with 4 decimals. No other text."
```

Paste the reply into `geo_provinces.py`:

```python
"""Carrier province codes and provincial capital coordinates.

Drafted by agy on 2026-09-15 and verified against OpenStreetMap (scripts/verify_provinces.py).
"""

PROVINCES: dict[str, tuple[str, float, float]] = {
    # 'HNI': ('Hà Nội', 21.0285, 105.8542), … one line per province from the agy reply
}
```

The table must contain at least `HNI`, `HCM`, `HPG`, `BN`, `TQG`, `VPC`, `DNG`; add any of these that agy left out by hand with the capital's coordinates.

- [ ] **Step 2: Verify every entry against Nominatim (one-off, not in tests)**

Create `scripts/verify_provinces.py`:

```python
"""Check PROVINCES against Nominatim: prints entries more than 25 km from OSM's answer."""

import sys
import time

import httpx

from vn_parcel_bot.services.geo import haversine_km
from vn_parcel_bot.services.geo_provinces import PROVINCES

HEADERS = {"User-Agent": "vn-parcel-bot/0.1 (personal Telegram parcel tracker)"}
bad = 0
with httpx.Client(headers=HEADERS, timeout=10) as client:
    for code, (name, lat, lon) in sorted(PROVINCES.items()):
        response = client.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": name, "countrycodes": "vn", "format": "jsonv2", "limit": 1},
        )
        hits = response.json()
        time.sleep(1.1)
        if not hits:
            print(f"{code} {name}: not found on OSM")
            bad += 1
            continue
        km = haversine_km((lat, lon), (float(hits[0]["lat"]), float(hits[0]["lon"])))
        if km > 25:
            print(f"{code} {name}: {km:.0f} km off; OSM {hits[0]['lat']}, {hits[0]['lon']}")
            bad += 1
print("entries needing a fix:", bad)
sys.exit(1 if bad else 0)
```

Run: `.venv/Scripts/python.exe scripts/verify_provinces.py` (after Step 4 so `haversine_km` exists). Fix each printed entry with OSM's coordinates and rerun until it prints `entries needing a fix: 0`.

- [ ] **Step 3: Write the failing tests**

```python
import pytest

from vn_parcel_bot import texts
from vn_parcel_bot.services.geo import PlaceParts, clean_place, format_distance, haversine_km
from vn_parcel_bot.services.geo_provinces import PROVINCES


@pytest.mark.parametrize(
    ("raw", "code", "district"),
    [
        ("21-HNI Thanh Tri 2 Hub", "HNI", "Thanh Tri"),
        ("24-HPG Hai An 3 Hub", "HPG", "Hai An"),
        ("BN B Mega SOC", "BN", None),
        ("11-TQG Son Duong Hub", "TQG", "Son Duong"),
        ("Bưu cục Quận 7", None, "Quận 7"),
        ("  Kho   HCM  ", None, "Kho HCM"),
    ],
)
def test_clean_place(raw, code, district):
    assert clean_place(raw) == PlaceParts(code, district)


def test_place_key_and_display():
    assert clean_place("21-HNI Thanh Tri 2 Hub").key == "HNI|Thanh Tri"
    assert clean_place("21-HNI Thanh Tri 2 Hub").display == "Kho Thanh Tri"
    assert clean_place("BN B Mega SOC").display == f"Kho {PROVINCES['BN'][0]}"
    assert clean_place("Bưu cục Quận 7").display == "Quận 7"


def test_haversine_and_distance_text():
    hanoi, haiphong = (21.03, 105.85), (20.86, 106.68)
    assert 85 < haversine_km(hanoi, haiphong) < 95
    assert haversine_km(hanoi, hanoi) == 0
    assert format_distance(0.4) == texts.DISTANCE_UNDER_1KM
    assert format_distance(4.54) == "~4.5 km"
    assert format_distance(12.4) == "~12 km"


def test_province_table_is_inside_vietnam():
    for required in ("HNI", "HCM", "HPG", "BN", "TQG", "VPC", "DNG"):
        assert required in PROVINCES
    for name, lat, lon in PROVINCES.values():
        assert name
        assert 8.0 <= lat <= 23.5 and 102.0 <= lon <= 110.0
```

- [ ] **Step 4: Implement `geo.py` (pure part) and `texts.DISTANCE_UNDER_1KM = "dưới 1 km"`**

```python
import math
import re
from dataclasses import dataclass

from vn_parcel_bot import texts
from vn_parcel_bot.services.geo_provinces import PROVINCES

_LEADING_NUMBER = re.compile(r"^\d{1,3}-")
_POST_OFFICE = re.compile(r"^bưu cục\s+", re.IGNORECASE)
_HUB_WORDS = frozenset({"hub", "soc", "mega", "lm", "kho", "bc"})
EARTH_RADIUS_KM = 6371.0


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


def clean_place(raw: str) -> PlaceParts:
    text = _POST_OFFICE.sub("", _LEADING_NUMBER.sub("", " ".join(raw.split())))
    tokens = text.split(" ") if text else []
    code = tokens.pop(0) if tokens and tokens[0] in PROVINCES else None
    dropped = False
    while tokens and tokens[-1].casefold() in _HUB_WORDS:
        tokens.pop()
        dropped = True
    while dropped and tokens and (tokens[-1].isdigit() or (len(tokens[-1]) == 1 and tokens[-1].isalpha())):
        tokens.pop()
    return PlaceParts(code, " ".join(tokens) or None)


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def format_distance(km: float) -> str:
    if km < 1:
        return texts.DISTANCE_UNDER_1KM
    if km < 10:
        return f"~{km:.1f} km"
    return f"~{round(km)} km"
```

Note `"  Kho   HCM  "`: `HCM` is not the first token, so no code; the trailing `HCM` is not a hub word, so the district stays `Kho HCM`.

- [ ] **Step 5: Run** `pytest tests/test_geo.py -q` → PASS; then run Step 2's verification script.
- [ ] **Step 6: Commit** `src/vn_parcel_bot/services/geo.py`, `geo_provinces.py`, `scripts/verify_provinces.py`, `tests/test_geo.py`, `texts.py` — "Place cleaning, distance and verified province table".

---

### Task 3: Geocoder with cache and rate limit

**Files:**
- Modify: `src/vn_parcel_bot/services/geo.py`
- Test: `tests/test_geocoder.py` (new)

**Interfaces:**
- Consumes: Task 1 `Repository.get_place`/`save_place`, Task 2 `clean_place`, `PROVINCES`.
- Produces: `NOMINATIM_URL`, `USER_AGENT`; `class Geocoder(repo, http: httpx.AsyncClient, now: Callable[[], datetime], sleep=asyncio.sleep, monotonic=time.monotonic)` with `async coordinates(raw_place: str) -> tuple[float, float] | None`.

- [ ] **Step 1: Write the failing tests**

```python
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from tests.fakes import FakeClock
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.geo import NOMINATIM_URL, USER_AGENT, Geocoder
from vn_parcel_bot.services.geo_provinces import PROVINCES

T0 = datetime(2026, 9, 15, 3, 0, tzinfo=UTC)


@pytest.fixture
async def env(tmp_path):
    repo = await Repository.open(tmp_path / "bot.sqlite3")
    clock = FakeClock(T0)
    sleeps: list[float] = []
    ticks = iter(float(n) for n in range(1000))

    async def sleep(seconds):
        sleeps.append(seconds)

    async with httpx.AsyncClient() as http:
        geocoder = Geocoder(repo, http, clock, sleep=sleep, monotonic=lambda: next(ticks) * 0.1)
        yield geocoder, repo, clock, sleeps
    await repo.close()


@respx.mock
async def test_district_found_on_osm_is_cached(env):
    geocoder, repo, _, _ = env
    route = respx.get(NOMINATIM_URL).mock(
        return_value=httpx.Response(200, json=[{"lat": "20.94", "lon": "105.84"}])
    )
    assert await geocoder.coordinates("21-HNI Thanh Tri 2 Hub") == (20.94, 105.84)
    assert await geocoder.coordinates("21-HNI Thanh Tri 3 Hub") == (20.94, 105.84)
    assert route.call_count == 1
    request = route.calls.last.request
    assert request.headers["User-Agent"] == USER_AGENT
    assert request.url.params["q"] == f"Thanh Tri, {PROVINCES['HNI'][0]}"
    assert request.url.params["countrycodes"] == "vn"
    assert (await repo.get_place("HNI|Thanh Tri")).source == "osm"


@respx.mock
async def test_province_centre_when_the_district_is_unknown(env):
    geocoder, repo, _, _ = env
    respx.get(NOMINATIM_URL).mock(return_value=httpx.Response(200, json=[]))
    _, lat, lon = PROVINCES["HPG"]
    assert await geocoder.coordinates("24-HPG Nowhere Hub") == (lat, lon)
    assert (await repo.get_place("HPG|Nowhere")).source == "province"


@respx.mock
async def test_province_only_hub_needs_no_request(env):
    geocoder, _, _, _ = env
    route = respx.get(NOMINATIM_URL)
    _, lat, lon = PROVINCES["BN"]
    assert await geocoder.coordinates("BN B Mega SOC") == (lat, lon)
    assert not route.called


@respx.mock
async def test_misses_are_cached_for_30_days(env):
    geocoder, _, clock, _ = env
    route = respx.get(NOMINATIM_URL).mock(return_value=httpx.Response(200, json=[]))
    assert await geocoder.coordinates("Bưu cục Không Có") is None
    assert await geocoder.coordinates("Bưu cục Không Có") is None
    assert route.call_count == 1
    clock.advance(timedelta(days=31))
    assert await geocoder.coordinates("Bưu cục Không Có") is None
    assert route.call_count == 2


@pytest.mark.parametrize("response", [httpx.Response(503), httpx.ConnectError("down")])
@respx.mock
async def test_errors_are_not_cached(env, response):
    geocoder, repo, _, _ = env
    kwargs = {"side_effect": response} if isinstance(response, Exception) else {"return_value": response}
    respx.get(NOMINATIM_URL).mock(**kwargs)
    assert await geocoder.coordinates("Bưu cục Quận 7") is None
    assert await repo.get_place("|Quận 7") is None


@respx.mock
async def test_requests_are_spaced(env):
    geocoder, _, _, sleeps = env
    respx.get(NOMINATIM_URL).mock(return_value=httpx.Response(200, json=[{"lat": "1", "lon": "2"}]))
    await geocoder.coordinates("Bưu cục A1")
    await geocoder.coordinates("Bưu cục A2")
    assert len(sleeps) == 1 and 1.0 < sleeps[0] <= 1.1
```

- [ ] **Step 2: Run** `pytest tests/test_geocoder.py -q` → FAIL (`ImportError: cannot import name 'Geocoder'`).

- [ ] **Step 3: Implement** — add to `geo.py` (imports `asyncio`, `logging`, `time`, `Callable`, `datetime`, `timedelta`, `httpx`, `Repository` under `TYPE_CHECKING`):

```python
log = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "vn-parcel-bot/0.1 (personal Telegram parcel tracker)"
MISS_RETRY_AFTER = timedelta(days=30)
MIN_REQUEST_GAP_SECONDS = 1.1


class Geocoder:
    def __init__(self, repo, http, now, sleep=asyncio.sleep, monotonic=time.monotonic) -> None:
        self._repo, self._http, self._now = repo, http, now
        self._sleep, self._monotonic = sleep, monotonic
        self._lock = asyncio.Lock()
        self._last_request: float | None = None

    async def coordinates(self, raw_place: str) -> tuple[float, float] | None:
        parts = clean_place(raw_place)
        if parts.code is None and parts.district is None:
            return None
        now = self._now()
        cached = await self._repo.get_place(parts.key)
        if cached is not None:
            if cached.source != "none" and cached.lat is not None and cached.lon is not None:
                return cached.lat, cached.lon
            if now - cached.looked_up_at < MISS_RETRY_AFTER:
                return None
        province = PROVINCES.get(parts.code) if parts.code else None
        if parts.district is not None:
            query = f"{parts.district}, {province[0]}" if province else parts.district
            try:
                hit = await self._search(query)
            except (httpx.HTTPError, ValueError) as exc:
                log.warning("place lookup failed type=%s", type(exc).__name__)
                return None
            if hit is not None:
                await self._repo.save_place(parts.key, hit[0], hit[1], "osm", now)
                return hit
        if province is not None:
            await self._repo.save_place(parts.key, province[1], province[2], "province", now)
            return province[1], province[2]
        await self._repo.save_place(parts.key, None, None, "none", now)
        return None

    async def _search(self, query: str) -> tuple[float, float] | None:
        async with self._lock:
            if self._last_request is not None:
                wait = MIN_REQUEST_GAP_SECONDS - (self._monotonic() - self._last_request)
                if wait > 0:
                    await self._sleep(wait)
            try:
                response = await self._http.get(
                    NOMINATIM_URL,
                    params={"q": query, "countrycodes": "vn", "format": "jsonv2", "limit": 1, "accept-language": "vi"},
                    headers={"User-Agent": USER_AGENT},
                    timeout=10,
                )
            finally:
                self._last_request = self._monotonic()
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])
```

(`float(...)` on a malformed answer raises `ValueError`/`KeyError`; wrap the last line in `try/except (KeyError, TypeError, ValueError): return None`.)

- [ ] **Step 4: Run** `pytest tests/test_geocoder.py tests/test_geo.py -q` → PASS.
- [ ] **Step 5: Commit** `geo.py`, `tests/test_geocoder.py` — "Geocoder: cached Nominatim lookups with province fallback".

---
### Task 4: Map renderer and tile cache

**Files:**
- Create: `src/vn_parcel_bot/services/maps.py`
- Modify: `pyproject.toml` (dependency `"pillow>=11"`), install with `.venv/Scripts/python.exe -m pip install -e .`
- Test: `tests/test_maps.py` (new)

**Interfaces:**
- Consumes: Task 3 `USER_AGENT`.
- Produces: `class MapError(Exception)`; `TileSource = Callable[[int, int, int], Awaitable[bytes]]`; `choose_zoom(home: tuple[float, float], place: tuple[float, float]) -> int`; `class TileCache(http, directory: Path, now=time.time, max_parallel=2)` with `async get(z: int, x: int, y: int) -> bytes`; `async render_map(home, place, tiles: TileSource) -> bytes` (PNG 600×400).

- [ ] **Step 1: Write the failing tests**

```python
import io
import os
import time

import httpx
import pytest
import respx
from PIL import Image

from vn_parcel_bot.services.maps import (
    HEIGHT, MAX_ZOOM, MIN_ZOOM, TILE_URL, WIDTH, MapError, TileCache, choose_zoom, render_map,
)

HOME = (21.03, 105.85)


def blank_tile() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (256, 256), (230, 230, 230)).save(buffer, "PNG")
    return buffer.getvalue()


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
    assert calls and all(0 <= y < 2**z for z, _, y in calls)


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
```

- [ ] **Step 2: Run** `pytest tests/test_maps.py -q` → FAIL (`ModuleNotFoundError: vn_parcel_bot.services.maps`).

- [ ] **Step 3: Implement `maps.py`**

```python
"""OpenStreetMap picture with the user's area, the hub pin and a dashed line."""

import asyncio
import io
import math
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

from vn_parcel_bot.services.geo import USER_AGENT

TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
TILE_SIZE = 256
WIDTH, HEIGHT = 600, 400
MIN_ZOOM, MAX_ZOOM = 5, 15
MARGIN = 40
AREA_RADIUS_M = 1000
TILE_MAX_AGE_SECONDS = 7 * 24 * 3600
ATTRIBUTION = "© OpenStreetMap contributors"

TileSource = Callable[[int, int, int], Awaitable[bytes]]
Point = tuple[float, float]


class MapError(Exception):
    pass


def world_px(point: Point, zoom: int) -> Point:
    lat, lon = point
    scale = TILE_SIZE * 2**zoom
    sin = math.sin(math.radians(lat))
    return (lon + 180) / 360 * scale, (0.5 - math.log((1 + sin) / (1 - sin)) / (4 * math.pi)) * scale


def area_radius_px(lat: float, zoom: int) -> float:
    return AREA_RADIUS_M / (156543.03392 * math.cos(math.radians(lat)) / 2**zoom)


def choose_zoom(home: Point, place: Point) -> int:
    for zoom in range(MAX_ZOOM, MIN_ZOOM - 1, -1):
        (hx, hy), (px, py) = world_px(home, zoom), world_px(place, zoom)
        pad = 2 * (area_radius_px(home[0], zoom) + MARGIN)
        if abs(hx - px) + pad <= WIDTH and abs(hy - py) + pad <= HEIGHT:
            return zoom
    return MIN_ZOOM


class TileCache:
    def __init__(self, http: httpx.AsyncClient, directory: Path, now=time.time, max_parallel: int = 2):
        self._http, self._directory, self._now = http, directory, now
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
                    TILE_URL.format(z=z, x=x, y=y), headers={"User-Agent": USER_AGENT}, timeout=15
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise MapError(type(exc).__name__) from exc
        await asyncio.to_thread(self._store, path, response.content)
        return response.content
```

`TileCache._fresh` uses the injected clock against the file's mtime; in the refresh test the clock moves 8 days ahead, so the cached file counts as stale.

```python
async def render_map(home: Point, place: Point, tiles: TileSource) -> bytes:
    zoom = choose_zoom(home, place)
    (hx, hy), (px, py) = world_px(home, zoom), world_px(place, zoom)
    left, top = (hx + px) / 2 - WIDTH / 2, (hy + py) / 2 - HEIGHT / 2
    count = 2**zoom
    coords = [
        (x, y)
        for x in range(math.floor(left / TILE_SIZE), math.floor((left + WIDTH - 1) / TILE_SIZE) + 1)
        for y in range(math.floor(top / TILE_SIZE), math.floor((top + HEIGHT - 1) / TILE_SIZE) + 1)
        if 0 <= y < count
    ]
    images = await asyncio.gather(*(tiles(zoom, x % count, y) for x, y in coords))
    radius = max(6.0, area_radius_px(home[0], zoom))
    return await asyncio.to_thread(
        _compose, coords, images, left, top, (hx - left, hy - top), (px - left, py - top), radius
    )


def _compose(coords, images, left, top, home_xy, place_xy, radius) -> bytes:
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), "white")
    for (x, y), data in zip(coords, images, strict=True):
        tile = Image.open(io.BytesIO(data)).convert("RGBA")
        canvas.paste(tile, (round(x * TILE_SIZE - left), round(y * TILE_SIZE - top)))
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    (hx, hy), (px, py) = home_xy, place_xy
    steps = max(1, int(math.hypot(px - hx, py - hy) // 12))
    for i in range(0, steps, 2):
        a, b = i / steps, min(1.0, (i + 1) / steps)
        draw.line((hx + (px - hx) * a, hy + (py - hy) * a, hx + (px - hx) * b, hy + (py - hy) * b),
                  fill=(40, 40, 40, 220), width=3)
    draw.ellipse((hx - radius, hy - radius, hx + radius, hy + radius),
                 fill=(30, 120, 255, 70), outline=(30, 120, 255, 255), width=3)
    draw.polygon(((px, py), (px - 9, py - 16), (px + 9, py - 16)), fill=(220, 40, 40, 255))
    draw.ellipse((px - 10, py - 30, px + 10, py - 10), fill=(220, 40, 40, 255), outline="white", width=2)
    text_box = draw.textbbox((0, 0), ATTRIBUTION)
    width, height = text_box[2] + 8, text_box[3] + 6
    draw.rectangle((WIDTH - width, HEIGHT - height, WIDTH, HEIGHT), fill=(255, 255, 255, 220))
    draw.text((WIDTH - width + 4, HEIGHT - height + 3), ATTRIBUTION, fill=(60, 60, 60, 255))
    buffer = io.BytesIO()
    Image.alpha_composite(canvas, overlay).convert("RGB").save(buffer, "PNG")
    return buffer.getvalue()
```

If Pillow's default font cannot draw `©`, replace it with `(c)` in `ATTRIBUTION` and keep the words.

- [ ] **Step 4: Run** `pytest tests/test_maps.py -q` → PASS; then `ruff check src/vn_parcel_bot/services/maps.py tests/test_maps.py --fix` and `ruff format` on both.
- [ ] **Step 5: Commit** `pyproject.toml`, `maps.py`, `tests/test_maps.py` — "Map renderer with cached OpenStreetMap tiles".

---

### Task 5: `place` hook for carrier modules

**Files:**
- Modify: `src/vn_parcel_bot/carriers/api.py`, `src/vn_parcel_bot/carriers/registry.py`, `src/vn_parcel_bot/carriers/modules/spx.py`
- Test: `tests/test_carrier_modules.py`, `tests/test_module_registry.py`

**Interfaces:**
- Produces: `api.event_location(event: TrackingEvent) -> str | None`; `CarrierModule.place: Callable[[TrackingEvent], str | None] = event_location`; `CarrierSnapshot.latest_place(carrier: str | None, events: Iterable[TrackingEvent]) -> str | None`; `spx.spx_place(event) -> str | None`.

- [ ] **Step 1: Stop the bot before touching carrier files**

```powershell
Stop-ScheduledTask -TaskName "VN Parcel Bot"
$procs = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -match 'vn_parcel_bot' -and $_.CommandLine -notmatch 'agy_proxy' })
foreach ($p in $procs) { try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch {} }
```

The bot stays stopped until Task 10 Step 4.

- [ ] **Step 2: Write the failing tests**

In `tests/test_carrier_modules.py`:

```python
from datetime import UTC, datetime, timedelta

from vn_parcel_bot.carriers.models import TrackingEvent
from vn_parcel_bot.carriers.modules.spx import spx_place

AT = datetime(2026, 9, 15, 1, 0, tzinfo=UTC)


def event(minutes, description, location=None):
    return TrackingEvent(time=AT + timedelta(minutes=minutes), description=description, location=location)


def test_spx_place_reads_the_hub_from_the_status_text():
    assert spx_place(event(0, "Đơn hàng đã đến kho 21-HNI Thanh Tri 2 Hub")) == "21-HNI Thanh Tri 2 Hub"
    assert spx_place(event(0, "Đơn hàng đã rời kho BN B Mega SOC")) == "BN B Mega SOC"
    assert spx_place(event(0, "Đang giao hàng")) is None
    assert spx_place(event(0, "Đơn hàng đã đến kho", location="Kho HCM")) == "Kho HCM"


def test_latest_place_takes_the_newest_event_with_a_place(snapshot):
    events = [
        event(0, "Đơn hàng đã đến kho 11-TQG Son Duong Hub"),
        event(30, "Đơn hàng đã đến kho 21-HNI Thanh Tri 2 Hub"),
        event(60, "Đang giao hàng"),
    ]
    assert snapshot.latest_place("spx", events) == "21-HNI Thanh Tri 2 Hub"
    assert snapshot.latest_place("jt", [event(0, "Đã đến", location=" Bưu cục  Quận 7 ")]) == "Bưu cục Quận 7"
    assert snapshot.latest_place(None, [event(0, "x")]) is None
```

In `tests/test_module_registry.py`, a module whose `place` raises:

```python
def test_a_failing_place_hook_gives_no_place(tmp_path, caplog):
    source = ALPHA.replace(
        'examples=(("AL00000001", True),),\n',
        'examples=(("AL00000001", True),),\n    place=lambda event: 1 / 0,\n',
    )
    snapshot = load(tmp_path, alpha=source).current
    from datetime import UTC, datetime
    from vn_parcel_bot.carriers.models import TrackingEvent
    event = TrackingEvent(time=datetime(2026, 9, 15, tzinfo=UTC), description="x", location="y")
    assert snapshot.latest_place("alpha", [event]) is None
    assert "carrier place failed carrier=alpha" in caplog.text
```

- [ ] **Step 3: Run** `pytest tests/test_carrier_modules.py tests/test_module_registry.py -q` → FAIL (`ImportError: cannot import name 'spx_place'`).

- [ ] **Step 4: Implement**

`api.py` — import `TrackingEvent` from `carriers.models`, add before `CarrierModule`:

```python
def event_location(event: TrackingEvent) -> str | None:
    return event.location
```

and a last field `place: Callable[[TrackingEvent], str | None] = event_location` with the comment `# the hub or place name shown on maps; default: the event's location`.

`registry.py` — import `event_location` and `TrackingEvent`; add to `CarrierSnapshot`:

```python
    def latest_place(self, carrier: str | None, events: Iterable[TrackingEvent]) -> str | None:
        module = self.get(carrier) if carrier is not None else None
        if module is None:
            return None
        for event in sorted(events, key=lambda item: item.time, reverse=True):
            try:
                value = module.place(event)
            except Exception as exc:
                log.warning("carrier place failed carrier=%s type=%s", carrier, type(exc).__name__)
                return None
            if isinstance(value, str) and value.strip():
                return " ".join(value.split())
        return None
```

`spx.py` — import `TrackingEvent` (already imported) and add:

```python
SPX_HUB = re.compile(r"(?:đã\s+)?(?:đến|rời|tại)\s+kho\s+(\S.*)$", re.IGNORECASE)


def spx_place(event: TrackingEvent) -> str | None:
    if event.location:
        return event.location
    match = SPX_HUB.search(event.description)
    return match.group(1).strip() if match else None
```

and `place=spx_place,` in `MODULE`.

- [ ] **Step 5: Run** `pytest tests/test_carrier_modules.py tests/test_module_registry.py tests/test_spx.py -q` → PASS.
- [ ] **Step 6: Commit** api, registry, spx and the two test files — "Carrier modules expose a place hook; SPX reads hubs from its status text".

---

### Task 6: `ParcelMaps`, setting, notifier photo and wiring

**Files:**
- Create: `src/vn_parcel_bot/services/parcel_maps.py`
- Modify: `src/vn_parcel_bot/config.py`, `src/vn_parcel_bot/texts.py`, `src/vn_parcel_bot/bot/notifier.py`, `src/vn_parcel_bot/bot/deps.py`, `src/vn_parcel_bot/bot/app.py`, `tests/fakes.py`, `.env.example`
- Test: `tests/test_parcel_maps.py` (new), `tests/test_config.py`, `tests/test_notifier.py`

**Interfaces:**
- Consumes: Task 1 repo, Task 2 `clean_place`/`haversine_km`/`format_distance`, Task 3 `Geocoder`, Task 4 `render_map`/`TileCache`/`MapError`.
- Produces: `Settings.maps_enabled: bool = True`; `texts.PLACE_LINE`, `PLACE_ONLY_LINE`, `MAP_CAPTION`; `TelegramNotifier.send_photo(chat_id: int, photo: bytes, caption: str, *, silent: bool = False) -> None` (and `FakeNotifier.send_photo` recording `photos: list[tuple[int, bytes, str, bool]]`); `class ParcelMaps(repo, geocoder, tiles: TileSource, settings)` with `async place_line(parcel: Parcel, user: User) -> str | None` (cache only, no network) and `async photo(parcel: Parcel, user: User) -> tuple[bytes, str] | None` (may look up and render; raises `MapError`); `Deps.maps: ParcelMaps | None = None`.

- [ ] **Step 1: Write the failing tests** (`tests/test_parcel_maps.py`)

```python
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from vn_parcel_bot import texts
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.maps import MapError
from vn_parcel_bot.services.parcel_maps import ParcelMaps

T0 = datetime(2026, 9, 15, 3, 0, tzinfo=UTC)
HUB = "21-HNI Thanh Tri 2 Hub"


class FakeGeocoder:
    def __init__(self, point=(20.94, 105.84)):
        self.point, self.calls = point, []

    async def coordinates(self, raw):
        self.calls.append(raw)
        return self.point


@pytest.fixture
async def env(tmp_path, settings):
    repo = await Repository.open(tmp_path / "bot.sqlite3")
    await repo.upsert_user(1, now=T0, is_allowed=True)
    parcel = await repo.add_parcel(
        user_id=1, carrier="spx", candidates=("spx",), tracking_number="SPXVN000000000001",
        phone_last4=None, now=T0, next_check_at=T0,
    )
    await repo.set_place(parcel.id, HUB)
    yield repo, settings, await repo.get_parcel(parcel.id)
    await repo.close()


async def tiles(z, x, y):
    from tests.test_maps import blank_tile
    return blank_tile()


async def test_place_line_without_home_shows_only_the_hub(env):
    repo, settings, parcel = env
    maps = ParcelMaps(repo, FakeGeocoder(), tiles, settings)
    assert await maps.place_line(parcel, await repo.get_user(1)) == texts.PLACE_ONLY_LINE.format(place="Kho Thanh Tri")


async def test_place_line_uses_only_the_cache(env):
    repo, settings, parcel = env
    await repo.set_home(1, 21.03, 105.85)
    geocoder = FakeGeocoder()
    maps = ParcelMaps(repo, geocoder, tiles, settings)
    user = await repo.get_user(1)
    assert await maps.place_line(parcel, user) == texts.PLACE_ONLY_LINE.format(place="Kho Thanh Tri")
    await repo.save_place("HNI|Thanh Tri", 20.94, 105.84, "osm", T0)
    line = await maps.place_line(parcel, user)
    assert line == texts.PLACE_LINE.format(place="Kho Thanh Tri", distance="~10 km")
    assert geocoder.calls == []


async def test_photo_needs_home_and_place_and_renders(env):
    repo, settings, parcel = env
    maps = ParcelMaps(repo, FakeGeocoder(), tiles, settings)
    assert await maps.photo(parcel, await repo.get_user(1)) is None
    await repo.set_home(1, 21.03, 105.85)
    png, caption = await maps.photo(parcel, await repo.get_user(1))
    assert png.startswith(b"\x89PNG")
    assert caption.startswith("🗺 <b>")
    assert "Kho Thanh Tri" in caption and "~10 km" in caption
    assert await ParcelMaps(repo, FakeGeocoder(None), tiles, settings).photo(parcel, await repo.get_user(1)) is None


async def test_photo_passes_render_failures_on(env):
    repo, settings, parcel = env
    await repo.set_home(1, 21.03, 105.85)

    async def broken(z, x, y):
        raise MapError("tile")

    with pytest.raises(MapError):
        await ParcelMaps(repo, FakeGeocoder(), broken, settings).photo(parcel, await repo.get_user(1))


async def test_maps_disabled_gives_nothing(env):
    repo, settings, parcel = env
    await repo.set_home(1, 21.03, 105.85)
    maps = ParcelMaps(repo, FakeGeocoder(), tiles, replace(settings, maps_enabled=False))
    user = await repo.get_user(1)
    assert await maps.place_line(parcel, user) is None
    assert await maps.photo(parcel, user) is None
```

`tests/test_config.py`: `MAPS_ENABLED` unset → `True`; `"false"`, `"0"`, `"off"` → `False`; `"maybe"` → `ConfigError` mentioning `MAPS_ENABLED`. `tests/test_notifier.py`: `send_photo` calls `bot.send_photo` with `photo`, `caption`, `parse_mode=HTML`, `disable_notification` and retries once after `RetryAfter` (copy the existing `send` retry test shape in that file).

- [ ] **Step 2: Run** `pytest tests/test_parcel_maps.py tests/test_config.py tests/test_notifier.py -q` → FAIL.

- [ ] **Step 3: Implement**

`texts.py`:

```python
PLACE_LINE = "📍 {place} · cách bạn {distance} (đường chim bay)"
PLACE_ONLY_LINE = "📍 {place}"
MAP_CAPTION = "🗺 <b>{title}</b>\n📍 {place} → khu vực của bạn · {distance} (đường chim bay)"
```

`config.py` — field `maps_enabled: bool = True`; in `from_env`:

```python
        maps_raw = (_get(env, "MAPS_ENABLED") or "true").lower()
        if maps_raw not in ("true", "1", "on", "yes", "false", "0", "off", "no"):
            errors.append("MAPS_ENABLED must be true or false")
        ...
            maps_enabled=maps_raw in ("true", "1", "on", "yes"),
```

`notifier.py`:

```python
    async def send_photo(self, chat_id: int, photo: bytes, caption: str, *, silent: bool = False) -> None:
        try:
            await self._with_retry(
                lambda: self._bot.send_photo(
                    chat_id=chat_id, photo=photo, caption=caption,
                    parse_mode=ParseMode.HTML, disable_notification=silent,
                )
            )
        except Forbidden:
            log.info("user %s blocked the bot", chat_id)
```

`tests/fakes.py` `FakeNotifier`: `self.photos: list[tuple[int, bytes, str, bool]] = []` and

```python
    async def send_photo(self, chat_id: int, photo: bytes, caption: str, *, silent: bool = False) -> None:
        self.photos.append((chat_id, photo, caption, silent))
```

`services/parcel_maps.py`:

```python
from html import escape

from vn_parcel_bot import texts
from vn_parcel_bot.config import Settings
from vn_parcel_bot.db.repo import Parcel, Repository, User
from vn_parcel_bot.services.formatting import parcel_title
from vn_parcel_bot.services.geo import Geocoder, clean_place, format_distance, haversine_km
from vn_parcel_bot.services.maps import TileSource, render_map


class ParcelMaps:
    def __init__(self, repo: Repository, geocoder: Geocoder, tiles: TileSource, settings: Settings) -> None:
        self._repo, self._geocoder, self._tiles, self._settings = repo, geocoder, tiles, settings

    def _display(self, parcel: Parcel) -> tuple[str, str] | None:
        if not self._settings.maps_enabled or not parcel.place:
            return None
        parts = clean_place(parcel.place)
        return (parts.key, escape(parts.display)) if parts.display else None

    async def place_line(self, parcel: Parcel, user: User) -> str | None:
        shown = self._display(parcel)
        if shown is None:
            return None
        key, name = shown
        cached = await self._repo.get_place(key)
        if user.home_lat is None or user.home_lon is None or cached is None or cached.lat is None or cached.lon is None:
            return texts.PLACE_ONLY_LINE.format(place=name)
        km = haversine_km((user.home_lat, user.home_lon), (cached.lat, cached.lon))
        return texts.PLACE_LINE.format(place=name, distance=format_distance(km))

    async def photo(self, parcel: Parcel, user: User) -> tuple[bytes, str] | None:
        shown = self._display(parcel)
        if shown is None or user.home_lat is None or user.home_lon is None:
            return None
        point = await self._geocoder.coordinates(parcel.place or "")
        if point is None:
            return None
        home = (user.home_lat, user.home_lon)
        png = await render_map(home, point, self._tiles)
        caption = texts.MAP_CAPTION.format(
            title=parcel_title(parcel), place=shown[1], distance=format_distance(haversine_km(home, point))
        )
        return png, caption
```

(`~10 km` in the tests: Hà Nội 21.03/105.85 to 20.94/105.84 is about 10.1 km.)

`deps.py`: field `maps: ParcelMaps | None = None`. `app.py` `_post_init` after building `http`:

```python
    geocoder = Geocoder(repo, http, _utc_now)
    tile_cache = TileCache(http, settings.db_path.parent / "tiles")
    maps = ParcelMaps(repo, geocoder, tile_cache.get, settings)
```

and pass `maps=maps` to `Deps(...)`. `.env.example`: `# Place lines and map pictures for parcels (true/false)` / `MAPS_ENABLED=true`.

- [ ] **Step 4: Run** `pytest tests/test_parcel_maps.py tests/test_config.py tests/test_notifier.py tests/test_app.py -q` → PASS.
- [ ] **Step 5: Commit** — "ParcelMaps joins places, distance and the map picture; MAPS_ENABLED; send_photo".

---
### Task 7: `/location` and the location message

**Files:**
- Modify: `src/vn_parcel_bot/texts.py`, `src/vn_parcel_bot/keyboards.py`, `src/vn_parcel_bot/bot/handlers_user.py`, `src/vn_parcel_bot/bot/commands.py`, `src/vn_parcel_bot/bot/app.py`
- Test: `tests/test_location.py` (new), `tests/test_app.py`

**Interfaces:**
- Consumes: Task 1 `set_home`/`clear_home`.
- Produces: `PENDING_LOCATION = "pending_location"` (in `PENDING_KEYS`, value `{"map_parcel": int | None}`); `location_request_keyboard() -> ReplyKeyboardMarkup`; handlers `location_cmd`, `location_message`; texts `LOCATION_ASK`, `LOCATION_STATUS`, `LOCATION_SAVED`, `LOCATION_CLEARED`, `LOCATION_NONE`, `BTN_SEND_LOCATION`, `BTN_CANCEL_TEXT`. `reply(update, text, reply_markup=...)` accepts inline or reply keyboards.

- [ ] **Step 1: Write the failing tests** (`tests/test_location.py`)

```python
import logging
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove

from vn_parcel_bot import texts
from vn_parcel_bot.bot.handlers_user import PENDING_LOCATION, cancel_cmd, location_cmd, location_message, text_message
from vn_parcel_bot.db.repo import Repository

T0 = datetime(2026, 9, 15, 3, 0, tzinfo=UTC)


class Msg:
    def __init__(self, sent, text=None, location=None):
        self.sent, self.text, self.location = sent, text, location
        self.message_id, self.caption, self.reply_to_message = 70, None, None

    async def reply_text(self, text, **kwargs):
        self.sent.append((text, kwargs.get("reply_markup")))
        return SimpleNamespace(message_id=71)


@pytest.fixture
async def env(settings):
    repo = await Repository.open(":memory:")
    await repo.upsert_user(1, now=T0, is_allowed=True)
    context = SimpleNamespace(bot_data={"deps": SimpleNamespace(repo=repo, settings=settings, maps=None)}, user_data={}, args=[])
    yield SimpleNamespace(repo=repo, context=context, sent=[])
    await repo.close()


def update(message):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=1, full_name="U", first_name="U"),
        effective_chat=SimpleNamespace(id=1),
        effective_message=message,
    )


async def test_location_command_offers_the_location_button(env):
    await location_cmd(update(Msg(env.sent, "/location")), env.context)
    text, markup = env.sent[-1]
    assert text == texts.LOCATION_ASK
    assert isinstance(markup, ReplyKeyboardMarkup)
    assert markup.keyboard[0][0].request_location is True
    assert markup.keyboard[1][0].text == texts.BTN_CANCEL_TEXT
    assert env.context.user_data[PENDING_LOCATION] == {"map_parcel": None}


async def test_shared_location_is_rounded_saved_and_not_logged(env, caplog):
    caplog.set_level(logging.DEBUG)
    await location_cmd(update(Msg(env.sent, "/location")), env.context)
    shared = SimpleNamespace(latitude=21.028511, longitude=105.854222)
    await location_message(update(Msg(env.sent, location=shared)), env.context)
    user = await env.repo.get_user(1)
    assert (user.home_lat, user.home_lon) == (21.03, 105.85)
    assert env.sent[-1][0] == texts.LOCATION_SAVED
    assert isinstance(env.sent[-1][1], ReplyKeyboardRemove)
    assert PENDING_LOCATION not in env.context.user_data
    assert "21.0" not in caplog.text and "105.8" not in caplog.text


async def test_status_and_off(env):
    await env.repo.set_home(1, 21.03, 105.85)
    await location_cmd(update(Msg(env.sent, "/location")), env.context)
    assert env.sent[-1][0] == texts.LOCATION_STATUS
    env.context.args = ["off"]
    await location_cmd(update(Msg(env.sent, "/location off")), env.context)
    assert env.sent[-1][0] == texts.LOCATION_CLEARED
    assert (await env.repo.get_user(1)).home_lat is None
    await location_cmd(update(Msg(env.sent, "/location off")), env.context)
    assert env.sent[-1][0] == texts.LOCATION_NONE


async def test_cancel_text_button_and_cancel_command_remove_the_keyboard(env):
    await location_cmd(update(Msg(env.sent, "/location")), env.context)
    await text_message(update(Msg(env.sent, texts.BTN_CANCEL_TEXT)), env.context)
    assert env.sent[-1][0] == texts.CANCELLED
    assert isinstance(env.sent[-1][1], ReplyKeyboardRemove)
    await location_cmd(update(Msg(env.sent, "/location")), env.context)
    env.context.bot = SimpleNamespace(delete_message=_no_delete)
    await cancel_cmd(update(Msg(env.sent, "/cancel")), env.context)
    assert isinstance(env.sent[-1][1], ReplyKeyboardRemove)


async def _no_delete(**kwargs):
    return None
```

`tests/test_app.py`: add `"location"` to `ALL_COMMANDS` and to the expected `BOT_COMMANDS` names right after `"phone"`; assert a `MessageHandler` for locations is registered (`any(isinstance(h, MessageHandler) and h.filters is not None and "LOCATION" in str(h.filters).upper() for h in group)`).

- [ ] **Step 2: Run** `pytest tests/test_location.py tests/test_app.py -q` → FAIL (`ImportError: cannot import name 'PENDING_LOCATION'`).

- [ ] **Step 3: Implement**

`texts.py`:

```python
LOCATION_ASK = (
    "📍 Bấm nút <b>Gửi vị trí</b> bên dưới. Mình chỉ lưu khu vực làm tròn ~1 km "
    "để tính khoảng cách tới đơn hàng."
)
LOCATION_STATUS = (
    "📍 Đã lưu khu vực của bạn (~1 km). Bấm <b>Gửi vị trí</b> để cập nhật, hoặc /location off để xóa."
)
LOCATION_SAVED = "📍 Đã lưu khu vực của bạn (làm tròn ~1 km)."
LOCATION_CLEARED = "📍 Đã xóa khu vực của bạn."
LOCATION_NONE = "Bạn chưa lưu khu vực nào. Gửi /location để lưu."
BTN_SEND_LOCATION = "📍 Gửi vị trí"
BTN_CANCEL_TEXT = "↩ Hủy"
```

and a `HELP` line after `/phone`: `"• /location – lưu khu vực của bạn (làm tròn ~1 km) để xem khoảng cách; /location off để xóa\n"`.

`keyboards.py`:

```python
from telegram import KeyboardButton, ReplyKeyboardMarkup

def location_request_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(texts.BTN_SEND_LOCATION, request_location=True)], [KeyboardButton(texts.BTN_CANCEL_TEXT)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
```

`handlers_user.py`:
- `reply(update, text, reply_markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | ReplyKeyboardRemove | None = None)`.
- `PENDING_LOCATION = "pending_location"` added to `PENDING_KEYS`.
- New handlers:

```python
async def location_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = get_deps(context)
    user = await current_user(update, deps)
    if [arg.casefold() for arg in (context.args or [])][:1] == ["off"]:
        if user.home_lat is None:
            await reply(update, texts.LOCATION_NONE)
            return
        await deps.repo.clear_home(user.telegram_id)
        log.info("home location cleared user=%s", user.telegram_id)
        await reply(update, texts.LOCATION_CLEARED)
        return
    drop_pending(context)
    user_data(context)[PENDING_LOCATION] = {"map_parcel": None}
    text = texts.LOCATION_STATUS if user.home_lat is not None else texts.LOCATION_ASK
    await reply(update, text, reply_markup=location_request_keyboard())


async def location_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    shared = getattr(message, "location", None)
    if message is None or shared is None:
        return
    deps = get_deps(context)
    user = await current_user(update, deps)
    await deps.repo.set_home(user.telegram_id, shared.latitude, shared.longitude)
    log.info("home location saved user=%s", user.telegram_id)
    user_data(context).pop(PENDING_LOCATION, None)
    await reply(update, texts.LOCATION_SAVED, reply_markup=ReplyKeyboardRemove())
```

- `text_message`, first thing after reading `data`:

```python
    if PENDING_LOCATION in data and message.text.strip() == texts.BTN_CANCEL_TEXT:
        data.pop(PENDING_LOCATION)
        await reply(update, texts.CANCELLED, reply_markup=ReplyKeyboardRemove())
        return
```

- `cancel_cmd`: `had_location = PENDING_LOCATION in data` before popping; reply `CANCELLED` with `reply_markup=ReplyKeyboardRemove() if had_location else None`.

`commands.py`: `("location", "Vị trí của bạn cho bản đồ")` after `("phone", …)`. `app.py`: register `("location", location_cmd)` in the command list and `app.add_handler(MessageHandler(filters.LOCATION & private, location_message))` before the text handler.

- [ ] **Step 4: Run** `pytest tests/test_location.py tests/test_app.py tests/test_label_flow.py -q` → PASS.
- [ ] **Step 5: Commit** — "/location saves a coarse home area through Telegram's location button".

---

### Task 8: Place line on cards and the 🗺 Bản đồ button

**Files:**
- Modify: `src/vn_parcel_bot/texts.py`, `src/vn_parcel_bot/keyboards.py`, `src/vn_parcel_bot/services/formatting.py`, `src/vn_parcel_bot/bot/handlers_user.py`, `src/vn_parcel_bot/bot/handlers_callback.py`
- Test: `tests/test_map_button.py` (new), `tests/test_keyboards.py`, `tests/test_formatting.py`

**Interfaces:**
- Consumes: Task 6 `ParcelMaps`, `Deps.maps`, `send_photo`; Task 7 `PENDING_LOCATION`, `location_request_keyboard`.
- Produces: `card_keyboard(parcel, *, page=None, maps=False)`; `format_parcel_card(parcel, tz, place_line: str | None = None)`; `handlers_user.card_view(deps, parcel, user_id) -> tuple[str, InlineKeyboardMarkup]`; `handlers_user.send_parcel_map(context, chat_id: int, user_id: int, parcel_id: int) -> str | None` (returns a failure text or `None` when the photo went out); texts `BTN_MAP`, `MAP_NO_PLACE`, `MAP_TOO_SOON`, `MAP_FAILED`; callback action `p:<id>:map`.

- [ ] **Step 1: Write the failing tests**

`tests/test_keyboards.py`:

```python
def test_card_keyboard_with_maps_moves_the_link_to_its_own_row():
    rows = card_keyboard(make_parcel(id=4), maps=True).inline_keyboard
    assert [b.callback_data for b in rows[2]] == ["p:4:shr", "p:4:map"]
    assert rows[3][0].url is not None
    assert len(card_keyboard(make_parcel(id=4)).inline_keyboard[2]) == 2  # unchanged without maps
```

`tests/test_formatting.py`:

```python
def test_parcel_card_appends_the_place_line():
    parcel = make_parcel(label="Áo", last_status_text="Đã đến kho", last_event_at=T0, progress=50)
    assert format_parcel_card(parcel, TZ, "📍 Kho Thanh Tri").endswith("\n📍 Kho Thanh Tri")
```

`tests/test_map_button.py` (reuse the fixtures of `tests/test_callback_handler.py` by importing `env`, `tap`, `add_spx`, `USER`, `CHAT` from it; give the env real `ParcelMaps` with a fake geocoder and blank tiles):

```python
import pytest

from tests.test_callback_handler import CHAT, SPX, USER, add_spx, env, tap  # noqa: F401
from tests.test_maps import blank_tile
from tests.test_parcel_maps import FakeGeocoder
from vn_parcel_bot import texts
from vn_parcel_bot.bot.handlers_user import PENDING_LOCATION, location_message
from vn_parcel_bot.services.maps import MapError
from vn_parcel_bot.services.parcel_maps import ParcelMaps


async def tiles(z, x, y):
    return blank_tile()


@pytest.fixture
def maps_env(env):
    env.deps.maps = ParcelMaps(env.repo, FakeGeocoder(), tiles, env.settings)
    return env


async def test_map_without_home_asks_for_the_location(maps_env):
    parcel = await add_spx(maps_env)
    await maps_env.repo.set_place(parcel.id, "21-HNI Thanh Tri 2 Hub")
    query = await tap(maps_env, f"p:{parcel.id}:map")
    assert query.answers == [None]
    assert maps_env.bot.sent[-1][1] == texts.LOCATION_ASK
    assert maps_env.context.user_data[PENDING_LOCATION] == {"map_parcel": parcel.id}


async def test_map_is_sent_as_a_photo_with_a_cooldown(maps_env):
    parcel = await add_spx(maps_env)
    await maps_env.repo.set_place(parcel.id, "21-HNI Thanh Tri 2 Hub")
    await maps_env.repo.set_home(USER, 21.03, 105.85)
    query = await tap(maps_env, f"p:{parcel.id}:map")
    assert query.answers == [None]
    chat_id, png, caption, silent = maps_env.deps.notifier.photos[-1]
    assert (chat_id, silent) == (CHAT, False) and png.startswith(b"\x89PNG") and "Kho Thanh Tri" in caption
    again = await tap(maps_env, f"p:{parcel.id}:map")
    assert again.answers == [texts.MAP_TOO_SOON]


async def test_map_without_a_place_or_on_failure(maps_env, monkeypatch):
    parcel = await add_spx(maps_env)
    await maps_env.repo.set_home(USER, 21.03, 105.85)
    assert (await tap(maps_env, f"p:{parcel.id}:map")).answers == [texts.MAP_NO_PLACE]
    await maps_env.repo.set_place(parcel.id, "21-HNI Thanh Tri 2 Hub")

    async def broken(*args, **kwargs):
        raise MapError("tile")

    monkeypatch.setattr(maps_env.deps.maps, "photo", broken)
    assert (await tap(maps_env, f"p:{parcel.id}:map")).answers == [texts.MAP_FAILED]


async def test_location_shared_for_a_map_sends_that_map(maps_env):
    parcel = await add_spx(maps_env)
    await maps_env.repo.set_place(parcel.id, "21-HNI Thanh Tri 2 Hub")
    await tap(maps_env, f"p:{parcel.id}:map")
    from tests.test_callback_handler import Msg, user_update
    from types import SimpleNamespace
    message = Msg(90, None, [])
    message.location = SimpleNamespace(latitude=21.03, longitude=105.85)
    await location_message(user_update(message), maps_env.context)
    assert maps_env.deps.notifier.photos
```

(`test_callback_handler.env` builds `Deps(..., FakeNotifier())`; the map handler sends through `deps.notifier`, so `FakeNotifier.photos` sees it.)

- [ ] **Step 2: Run** `pytest tests/test_map_button.py tests/test_keyboards.py tests/test_formatting.py -q` → FAIL.

- [ ] **Step 3: Implement**

`texts.py`: `BTN_MAP = "🗺 Bản đồ"`, `MAP_NO_PLACE = "Đơn này chưa có vị trí kho để vẽ bản đồ."`, `MAP_TOO_SOON = "Bạn vừa xem bản đồ đơn này, thử lại sau ít phút nhé."`, `MAP_FAILED = "Không vẽ được bản đồ lúc này, bạn thử lại sau nhé."`.

`keyboards.card_keyboard(parcel, *, page=None, maps=False)`: third row is `[share, link]` when `maps` is false; when true it is `[share, _button(texts.BTN_MAP, f"{prefix}:map{suffix}")]` followed by a row `[link]`.

`formatting.format_parcel_card(parcel, tz, place_line=None)`: `if place_line: lines.append(place_line)` before joining.

`handlers_user.py`:

```python
MAP_COOLDOWN_SECONDS = 60
MAP_SENDS = "map_sends"


async def card_view(deps: Deps, parcel: Parcel, user_id: int, page: int | None = None) -> tuple[str, InlineKeyboardMarkup]:
    maps = deps.maps if deps.maps is not None and deps.settings.maps_enabled else None
    line = None
    if maps is not None:
        user = await deps.repo.get_user(user_id)
        line = await maps.place_line(parcel, user) if user is not None else None
    return format_parcel_card(parcel, deps.settings.tz, line), card_keyboard(parcel, page=page, maps=maps is not None)


async def send_parcel_map(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, parcel_id: int) -> str | None:
    deps = get_deps(context)
    parcel = await deps.repo.get_parcel(parcel_id)
    user = await deps.repo.get_user(user_id)
    if deps.maps is None or parcel is None or user is None or parcel.user_id != user_id:
        return texts.CARD_NOT_FOUND
    if not parcel.place:
        return texts.MAP_NO_PLACE
    sends: dict[int, float] = context.bot_data.setdefault(MAP_SENDS, {})
    now = time.monotonic()
    if now - sends.get(parcel_id, -MAP_COOLDOWN_SECONDS) < MAP_COOLDOWN_SECONDS:
        return texts.MAP_TOO_SOON
    try:
        made = await deps.maps.photo(parcel, user)
    except MapError as exc:
        log.warning("map failed type=%s", type(exc).__name__)
        return texts.MAP_FAILED
    if made is None:
        return texts.MAP_NO_PLACE
    sends[parcel_id] = now
    await deps.notifier.send_photo(chat_id, made[0], made[1])
    return None
```

- `location_message`: take `pending = user_data(context).pop(PENDING_LOCATION, None) or {}`; after `LOCATION_SAVED`, `if pending.get("map_parcel") is not None:` call `failure = await send_parcel_map(context, _chat_id(update) or user.telegram_id, user.telegram_id, pending["map_parcel"])` and reply `failure` when it is not `None`.
- `_refresh_card` and `_open_share` use `card_view` for text and keyboard.

`handlers_callback.py`:
- `card`/`dno` and `_check` render through `card_view(deps, parcel, user_id, page)`.
- New action:

```python
    elif action == "map":
        await _map(context, query, parcel)
```

```python
async def _map(context: ContextTypes.DEFAULT_TYPE, query: CallbackQuery, parcel: Parcel) -> None:
    deps = get_deps(context)
    user = await deps.repo.get_user(query.from_user.id)
    chat_id = _chat_id(query)
    if deps.maps is None or user is None or chat_id is None:
        await query.answer()
        return
    if user.home_lat is None:
        await query.answer()
        drop_pending(context)
        user_data(context)[PENDING_LOCATION] = {"map_parcel": parcel.id}
        await context.bot.send_message(
            chat_id, texts.LOCATION_ASK, parse_mode=ParseMode.HTML, reply_markup=location_request_keyboard()
        )
        return
    failure = await send_parcel_map(context, chat_id, user.telegram_id, parcel.id)
    await query.answer(failure)
```

- [ ] **Step 4: Run** `pytest tests/test_map_button.py tests/test_callback_handler.py tests/test_button_prompts.py tests/test_keyboards.py tests/test_formatting.py tests/test_location.py -q` → PASS.
- [ ] **Step 5: Commit** — "Cards show the hub and distance; 🗺 Bản đồ sends the map".

---

### Task 9: Poller keeps the place and sends the map after a hub change

**Files:**
- Modify: `src/vn_parcel_bot/services/poller.py`, `src/vn_parcel_bot/services/parcel_maps.py`, `src/vn_parcel_bot/services/formatting.py`, `src/vn_parcel_bot/bot/app.py`
- Test: `tests/test_poller_maps.py` (new), `tests/test_parcel_maps.py`

**Interfaces:**
- Consumes: Task 5 `CarrierSnapshot.latest_place`; Task 6 `ParcelMaps`, `send_photo`.
- Produces: `Poller(..., rand=random.random, maps: ParcelMaps | None = None)`; `ParcelMaps.prepare(place: str) -> None` (looks the place up when maps are enabled); `format_event_update(..., place_line: str | None = None)`.

- [ ] **Step 1: Write the failing tests** (`tests/test_poller_maps.py`)

```python
import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from tests.fakes import FakeCarrier, FakeClock, FakeNotifier, fake_registry, found
from tests.test_maps import blank_tile
from tests.test_parcel_maps import FakeGeocoder
from vn_parcel_bot import texts
from vn_parcel_bot.carriers.models import TrackingEvent
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.maps import MapError
from vn_parcel_bot.services.parcel_maps import ParcelMaps
from vn_parcel_bot.services.poller import Poller

T0 = datetime(2026, 9, 15, 3, 0, tzinfo=UTC)
SPX = "SPXVN000000000001"


def hub(minutes, name):
    return TrackingEvent(time=T0 + timedelta(minutes=minutes), description=f"Đơn hàng đã đến kho {name}")


async def tiles(z, x, y):
    return blank_tile()


@pytest.fixture
async def env(settings):
    repo = await Repository.open(":memory:")
    await repo.upsert_user(1, now=T0, is_allowed=True)
    carrier = FakeCarrier("spx")
    clock = FakeClock(T0)
    notifier = FakeNotifier()
    maps = ParcelMaps(repo, FakeGeocoder(), tiles, settings)

    async def no_sleep(seconds):
        return None

    async with httpx.AsyncClient() as http:
        poller = Poller(repo, fake_registry({"spx": carrier}), http, notifier, settings, clock, no_sleep, lambda: 0.0, maps=maps)
        parcel = await repo.add_parcel(
            user_id=1, carrier="spx", candidates=("spx",), tracking_number=SPX,
            phone_last4=None, now=T0, next_check_at=T0,
        )
        yield poller, repo, carrier, clock, notifier, maps, parcel
    await repo.close()


async def test_new_hub_sends_update_then_map(env):
    poller, repo, carrier, _, notifier, _, parcel = env
    await repo.set_home(1, 21.03, 105.85)
    carrier.results[(SPX, None)] = found("spx", SPX, hub(0, "21-HNI Thanh Tri 2 Hub"))
    await poller.run_cycle()
    assert (await repo.get_parcel(parcel.id)).place == "21-HNI Thanh Tri 2 Hub"
    assert "📍 Kho Thanh Tri · cách bạn ~10 km" in notifier.sent[-1][1]
    assert len(notifier.photos) == 1 and notifier.photos[0][3] is True


async def test_same_hub_is_not_mapped_twice(env):
    poller, repo, carrier, clock, notifier, _, _ = env
    await repo.set_home(1, 21.03, 105.85)
    carrier.results[(SPX, None)] = found("spx", SPX, hub(0, "21-HNI Thanh Tri 2 Hub"))
    await poller.run_cycle()
    carrier.results[(SPX, None)] = found(
        "spx", SPX, hub(0, "21-HNI Thanh Tri 2 Hub"),
        TrackingEvent(time=T0 + timedelta(minutes=5), description="Đang giao hàng"),
    )
    clock.advance(timedelta(minutes=20))
    await poller.run_cycle()
    assert len(notifier.sent) == 2
    assert len(notifier.photos) == 1


async def test_without_home_the_place_is_kept_and_no_map_is_sent(env):
    poller, repo, carrier, _, notifier, _, parcel = env
    carrier.results[(SPX, None)] = found("spx", SPX, hub(0, "21-HNI Thanh Tri 2 Hub"))
    await poller.run_cycle()
    assert (await repo.get_parcel(parcel.id)).place == "21-HNI Thanh Tri 2 Hub"
    assert notifier.sent[-1][1].endswith(texts.PLACE_ONLY_LINE.format(place="Kho Thanh Tri"))
    assert notifier.photos == []


async def test_map_failure_still_sends_the_update(env, monkeypatch, caplog):
    poller, repo, carrier, _, notifier, maps, _ = env
    caplog.set_level(logging.WARNING)
    await repo.set_home(1, 21.03, 105.85)

    async def broken(*args, **kwargs):
        raise MapError("tile")

    monkeypatch.setattr(maps, "photo", broken)
    carrier.results[(SPX, None)] = found("spx", SPX, hub(0, "21-HNI Thanh Tri 2 Hub"))
    await poller.run_cycle()
    assert len(notifier.sent) == 1 and notifier.photos == []
    assert "map failed type=MapError" in caplog.text
```

`tests/test_parcel_maps.py`: `prepare` calls the geocoder once when enabled and never when `maps_enabled=False`.

- [ ] **Step 2: Run** `pytest tests/test_poller_maps.py tests/test_parcel_maps.py -q` → FAIL (`TypeError: Poller.__init__() got an unexpected keyword argument 'maps'`).

- [ ] **Step 3: Implement**

`parcel_maps.py`:

```python
    async def prepare(self, place: str) -> None:
        if self._settings.maps_enabled:
            await self._geocoder.coordinates(place)
```

`formatting.format_event_update(..., progress=None, place_line=None)`: append `place_line` as the last line when given (after the delivered/returned footer).

`poller.py`:
- `__init__` gains `maps: ParcelMaps | None = None` (stored as `self._maps`).
- In `_handle_result`, inside `if result.found:` right after `record_check_success(...)`:

```python
            moved = False
            if self._maps is not None:
                place = self._registry.current.latest_place(result.carrier, result.events)
                if place is not None and place != parcel.place:
                    await self._repo.set_place(parcel.id, place)
                    await self._maps.prepare(place)
                    moved = True
```

- In the `if new or newly_delivered or newly_returned:` block, fetch `current` and the user before building the text, and pass the line:

```python
                current = await self._repo.get_parcel(parcel.id)
                user = await self._repo.get_user(parcel.user_id)
                place_line = (
                    await self._maps.place_line(current, user)
                    if self._maps is not None and current is not None and user is not None
                    else None
                )
                text = format_event_update(..., place_line=place_line)
```

  and after `await self._notify(...)`:

```python
                if moved and self._maps is not None and current is not None and user is not None:
                    await self._send_map(current, user)
```

- New method:

```python
    async def _send_map(self, parcel: Parcel, user: User) -> None:
        try:
            made = await self._maps.photo(parcel, user) if self._maps is not None else None
        except MapError as exc:
            log.warning("map failed type=%s", type(exc).__name__)
            return
        if made is not None:
            await self._notifier.send_photo(parcel.user_id, made[0], made[1], silent=True)
```

  (`Notifier` protocol gains `send_photo`.)

`app.py`: build `geocoder`, `tile_cache` and `maps` before `Poller`, and construct `Poller(repo, registry, http, notifier, settings, _utc_now, maps=maps)`.

- [ ] **Step 4: Run** `pytest tests/test_poller_maps.py tests/test_poller.py tests/test_parcel_maps.py tests/test_app.py -q` → PASS.
- [ ] **Step 5: Commit** — "Poller stores the hub and sends the map after a hub change".

---

### Task 10: Docs, gates and going live

**Files:**
- Modify: `BUILD_PLAN.md`, `SPEC.md` (regenerated), `README.md`, `.env.example`

- [ ] **Step 1: BUILD_PLAN 2.8** — version line `Version 2.8`; a `## Changes in 2.8 (2026-09-15)` entry summarising schema v4, `/location`, the `place` hook, geocoder, map picture, card button, automatic maps and `MAPS_ENABLED` (link the spec); §4 command table row `| /location | [off] | Save the coarse home area through Telegram's location button (rounded to 2 decimals) or delete it |`; §10.1 row `| MAPS_ENABLED | no | true | true/false |`; §9.2 constants note for `MAP_COOLDOWN_SECONDS = 60`. Regenerate `SPEC.md` with the same generator used for 2.7 (Part 2 between `# Part 2 — Specification` and `# Part 3 — Prompts`, trailing `---` removed, header with the version).
- [ ] **Step 2: README** — a "Maps and distance" section: `/location` once, what is stored (~1 km), the 🗺 Bản đồ button, automatic maps after hub changes, straight-line distance, OpenStreetMap credit, `MAPS_ENABLED`; commands table row for `/location`; `.env` table row for `MAPS_ENABLED`.
- [ ] **Step 3: Gates** — `ruff check .`, `ruff format --check .`, `pytest -q` all green.
- [ ] **Step 4: Go live** — commit the docs; start the bot again:

```powershell
Start-ScheduledTask -TaskName "VN Parcel Bot"
```

  After 60 s check `logs/bot.log` for `bot started as` and no `Traceback`/`rejected`; confirm `data/bot.sqlite3.bak-v3` exists and `PRAGMA user_version` is 4; after the next poll check (read-only, no codes) that active SPX parcels have `place` set.
- [ ] **Step 5: Report** — tell the user to send `/location` and tap 🗺 Bản đồ on a card; nothing is pushed to GitHub unless asked.
