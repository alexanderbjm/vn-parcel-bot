# Parcel maps: hub location, distance and map picture — design

Date: 2026-09-15 · Branch: `main` · Status: built 2026-09-15 (plan `docs/superpowers/plans/2026-09-15-parcel-maps.md`)

## Amendment (2026-09-15): map data providers

openstreetmap.org is unreachable from the bot's PC (www, tile and nominatim hosts all reset the connection, also with curl: a network-level block). With the user's approval the bot uses:

- **Place search: Photon** (`https://photon.komoot.io/api/`, OpenStreetMap data) instead of Nominatim: params `q`, `limit=1`, `bbox=102.1,8.1,109.5,23.4` (Vietnam); the answer is GeoJSON (`features[0].geometry.coordinates` = `[lon, lat]`). Same User-Agent, 1.1 s spacing, caching and error rules as §5.3.
- **Map squares: CARTO Voyager** (`https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png`) instead of `tile.openstreetmap.org`; same concurrency and 7-day cache as §6.1. The picture credits `© OpenStreetMap contributors © CARTO`.

Every mention of Nominatim or `tile.openstreetmap.org` below means these providers.

## 1. Why

The user wants to see how far a parcel is from them: a map picture with the parcel's current hub and their own area, and a distance. The request named agy; agy is used offline to draft the province table (§5.2), not to screenshot maps (Google Maps terms forbid automated screenshots, and agy would need browser and web access that was deliberately removed from it).

## 2. Decisions (from the chat)

| Topic | Decision |
|---|---|
| User location | Shared once through Telegram's location button; stored rounded to 2 decimals (~1 km); `/location off` deletes it |
| Visual | A drawn map picture with both points (hub pin, user area circle, dashed line) from OpenStreetMap tiles |
| When | Automatically after an update that moves the parcel to a new hub, and on a card button |
| Hub → coordinates | Province code table (drafted by agy, verified) plus a cached OpenStreetMap Nominatim lookup for the district; province centre as fallback |
| Distance | Straight line, labelled "đường chim bay" |

Out of scope: road distance or routing, live location, courier position, Google Maps, agy browser screenshots, group chats, maps for parcels without a hub.

## 3. Data (schema v4)

Migration 3 writes `<db_path>.bak-v3` first (as earlier migrations), then:

- `users.home_lat REAL`, `users.home_lon REAL` — both NULL or both set; values rounded with `round(x, 2)`.
- `parcels.place TEXT` — the cleaned name of the parcel's latest hub (§5.1), NULL until one is seen.
- New table `places(name TEXT PRIMARY KEY, lat REAL, lon REAL, source TEXT NOT NULL CHECK (source IN ('osm', 'province', 'none')), looked_up_at TEXT NOT NULL)`. `none` rows have NULL coordinates.

Repository additions: `set_home(user_id, lat, lon)`, `clear_home(user_id)`, `set_place(parcel_id, name, now)`, `get_place(name)`, `save_place(name, lat, lon, source, now)`. `User` gains `home_lat`, `home_lon`; `Parcel` gains `place`.

## 4. The user's location

- `/location` without arguments replies `LOCATION_ASK` (or `LOCATION_STATUS` when one is saved) with a one-time reply keyboard: `[📍 Gửi vị trí]` (`request_location=True`) and `[↩ Hủy]` (plain text). `PENDING_LOCATION` is set, holding an optional parcel id for a map that asked for it (§6.2).
- A location message (private chat, `filters.LOCATION`, live or static) from an allowed user: round both coordinates to 2 decimals, `set_home`, reply `LOCATION_SAVED` with `ReplyKeyboardRemove`, clear `PENDING_LOCATION`; if it held a parcel id, send that parcel's map (§6.2).
- The text `↩ Hủy` while `PENDING_LOCATION` is set → `CANCELLED` with `ReplyKeyboardRemove`. `/cancel` clears it too.
- `/location off` → `clear_home` → `LOCATION_CLEARED`; nothing saved → `LOCATION_NONE`.
- Coordinates are never logged (only `"home location saved user=%s"` / `"home location cleared user=%s"`), never sent to Nominatim, and never shown back as numbers.
- Every map and distance uses the location of the user who receives the message (a shared parcel shows the distance to the recipient's area).

## 5. Hub and coordinates

### 5.1 Where the place comes from

- `CarrierModule` gains `place: Callable[[TrackingEvent], str | None] = event_location`, where `event_location` returns `event.location`.
- `spx.py` sets `place=spx_place`: the text after `(?:đã )?(?:đến|rời|tại) kho ` in the description, if any (e.g. `Đơn hàng đã đến kho 21-HNI Thanh Tri 2 Hub` → `21-HNI Thanh Tri 2 Hub`).
- The poller takes the newest event (by time) for which the module's `place` returns a value, cleans it (§5.2) and compares it with `parcel.place`. Events without a place (e.g. "Đang giao hàng") keep the stored place.
- Because `api.py` changes, the bot must restart on the new `api.py` before any module file using `place=` is saved (a running bot would reject the module and alert the admin, as happened on 2026-09-15 with `code_lengths`). The build plan stops the task while editing modules.

### 5.2 Cleaning and the province table

- Cleaning: collapse spaces; drop a leading `NN-`; the first token, if it is 2–3 uppercase letters found in the province table, is the province code; drop trailing tokens that are digits, single letters or one of `Hub`, `SOC`, `Mega`, `LM`, `Kho`, `Bưu cục`, `BC`. The rest is the district. Examples: `21-HNI Thanh Tri 2 Hub` → code `HNI`, district `Thanh Tri`; `BN B Mega SOC` → code `BN`, no district; `Bưu cục Quận 7` → no code, district `Quận 7`.
- `services/geo_provinces.py`: `PROVINCES: dict[str, tuple[str, float, float]]` — carrier province code → (Vietnamese province name, lat, lon of the provincial capital). agy drafts it in print mode with no tools (text only); every entry is verified at build time by looking up the province name on Nominatim (§5.3) and rejecting entries more than 25 km from the answer. The table is committed; the bot never regenerates it.

### 5.3 Lookup (`services/geo.py`)

- `Geocoder(repo, http, now, sleep)`. `coordinates(place_name) -> tuple[float, float] | None`:
  1. Cached row in `places`: `osm` or `province` → its coordinates; `none` younger than 30 days → `None`.
  2. District present → Nominatim `GET https://nominatim.openstreetmap.org/search` with `q="<district>, <province name>"` (or just the district when there is no code), `countrycodes=vn`, `format=jsonv2`, `limit=1`, `accept-language=vi`, header `User-Agent: vn-parcel-bot/<version> (personal Telegram parcel tracker)`, timeout 10 s. A hit → save `osm`.
  3. Otherwise a known province code → save `province` with the table's centre.
  4. Otherwise save `none`.
- One request at a time with at least 1.1 s between Nominatim requests (lock + monotonic clock), as its usage policy requires. HTTP errors and timeouts are not cached and return `None`; they are logged at WARNING with the error type.
- Lookups run in the poller when a parcel's place changes, never while rendering a card.

### 5.4 Distance

- Haversine on a 6371 km sphere from `(home_lat, home_lon)` to the place.
- `format_distance(km)`: `< 1` → `DISTANCE_UNDER_1KM`; `< 10` → one decimal (`~4.5 km`); otherwise whole km (`~12 km`).
- `PLACE_LINE = "📍 {place} · cách bạn {distance} (đường chim bay)"`, shown as the last line of the parcel card and of update messages when the user has a home, the parcel has a place and the place has coordinates. Without a home: `PLACE_ONLY_LINE = "📍 {place}"`. `{place}` is the cleaned, escaped place name, prefixed with `Kho ` when it came from an SPX hub.

## 6. Map picture

### 6.1 Rendering (`services/maps.py`)

- Pillow (new dependency `pillow>=11`) plus the existing `httpx` client; no `staticmap` package (unmaintained, pulls in `requests`).
- `render_map(home, place, *, tiles) -> bytes` (PNG, 600×400): Web Mercator; the zoom is the largest in 5..15 at which both points plus a 1 km circle and a 40 px margin fit; the view is centred on their midpoint.
- Tiles: `https://tile.openstreetmap.org/{z}/{x}/{y}.png` with the bot's User-Agent, at most 2 concurrent requests, cached as `data/tiles/{z}/{x}/{y}.png` and reused for 7 days. Any failed tile raises `MapError`.
- Drawing: user area as a translucent blue circle of 1 km radius (no exact pin), hub as a red pin, a dashed line between them, and `© OpenStreetMap contributors` bottom right on a white box (OSM attribution requirement).
- Compositing runs in `asyncio.to_thread`.

### 6.2 Sending

- `Notifier.send_photo(chat_id, png, caption, *, silent)` (HTML caption, one `RetryAfter` retry like `send`).
- Caption `MAP_CAPTION = "🗺 <b>{title}</b>\n📍 {place} → khu vực của bạn · {distance} (đường chim bay)"` (title = `parcel_title`, code blurred).
- Automatic: after the poller sends an update whose cleaned place differs from `parcel.place`, it calls `set_place` and, when the user has a home and the geocoder returns coordinates, sends the map silently right after the update. A place first seen while the user has no home is stored but not mapped later.
- Card button: `card_keyboard` rows become `[✏️ Đổi tên] [📜 Hành trình]`, `[🔄 Kiểm tra] [🗑 Xóa]`, `[📤 Chia sẻ] [🗺 Bản đồ]`, `[🔗 Tra cứu … ↗]` (+ `[⬅ Danh sách]`). Callback `p:<id>:map`:
  - no home → answer, send `LOCATION_ASK` with the location keyboard and set `PENDING_LOCATION = {"map_parcel": id}`;
  - no place or no coordinates → toast `MAP_NO_PLACE`;
  - same parcel mapped less than 60 s ago (in memory) → toast `MAP_TOO_SOON`;
  - otherwise render and send the photo; `MapError` → toast `MAP_FAILED`.
- Failures never block the update text; they are logged with the error type only.

## 7. Settings, commands and texts

- `.env`: `MAPS_ENABLED` (default `true`; `false`, `0` or `off` disables place lines, map buttons, automatic maps and lookups).
- `BOT_COMMANDS` gains `("location", "Vị trí của bạn cho bản đồ")`; `HELP` gains `• /location – lưu khu vực của bạn (làm tròn ~1 km) để xem khoảng cách; /location off để xóa`.
- New texts: `LOCATION_ASK`, `LOCATION_STATUS`, `LOCATION_SAVED`, `LOCATION_CLEARED`, `LOCATION_NONE`, `BTN_SEND_LOCATION`, `BTN_CANCEL_TEXT`, `BTN_MAP`, `PLACE_LINE`, `PLACE_ONLY_LINE`, `DISTANCE_UNDER_1KM`, `MAP_CAPTION`, `MAP_NO_PLACE`, `MAP_TOO_SOON`, `MAP_FAILED`.

## 8. Testing (no network)

- Cleaning and SPX place extraction: a table of real-shaped hub strings (no tracking codes).
- Haversine and `format_distance` bounds; province table sanity (every entry inside Vietnam's bounding box).
- Geocoder with respx and a fake clock: cache hits, `none` retried after 30 days, errors not cached, 1.1 s spacing, User-Agent sent, province fallback.
- Renderer with a fake tile source (blank 256 px tiles): PNG 600×400, zoom choice for near and far points, tile cache freshness, `MapError` on a failed tile.
- Migration v4: backup written, columns and table present, existing rows kept.
- Handlers: location saved rounded and never logged, `/location off`, `↩ Hủy`, map button without a home prompts for the location and then sends the map, cooldown, failure toast.
- Poller: new hub → update then photo; same hub → no photo; no home → place stored, no photo; render failure → update still sent.
- Keyboards: new card layout and callback data under 64 bytes.

## 9. Build order

The buttons and multi-remove design (proposed 2026-09-15) is still waiting for approval; either can be built first. This feature gets its own plan (`docs/superpowers/plans/2026-09-15-parcel-maps.md`), a docs version bump, and a restart with the task stopped while module files change (§5.1).
