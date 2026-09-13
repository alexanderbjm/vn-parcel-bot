# vn-parcel-bot — Specification

Version 1.0 · 2026-09-11 · Status: draft for review

Standalone copy of **Part 2** of `BUILD_PLAN.md`, extracted unchanged on 2026-09-11. `BUILD_PLAN.md` stays the canonical copy: its build prompts (Part 3) cite these sections as `§N`. When the spec changes, edit Part 2 of `BUILD_PLAN.md` and re-extract this file so the two never drift apart.

If code and this spec disagree, the spec wins; if the spec is wrong, fix the spec first, then the code.

---

## 1. Overview

A personal Telegram bot, running on a Windows 10 PC in Vietnam, that watches parcels shipped by **SPX Express Vietnam** and **J&T Express Vietnam** and messages the owner of each parcel **every time a new tracking event appears**.

- Users are **buyers** receiving parcels. They add parcels by **pasting a tracking code** into a private chat with the bot.
- Used by the **admin (owner) plus a few allowlisted family/friends**. Each person sees and is notified only about their own parcels.
- The bot **polls the carriers' public tracking endpoints** directly (no paid aggregator) and uses Telegram **long polling** (no public URL, no webhook, no port forwarding).

## 2. Scope

In scope (v1):
- Carriers: SPX Express VN, J&T Express VN.
- Private chats only (groups are ignored).
- Commands and flows in §4; polling and notifications in §6.
- Runs as a background process started at Windows logon (§12).
- Vietnamese user interface (all strings in one module, §17).

Out of scope (v1): see §16.

## 3. Users and access

| Role | How assigned | Can |
|---|---|---|
| Admin | `ADMIN_TELEGRAM_ID` in `.env`; upserted with `is_admin=1, is_allowed=1` on every start | Everything members can, plus `/allow`, `/revoke`, `/users`, `/health`; receives operational alerts |
| Member | Admin runs `/allow <telegram_id> [name]` | Track, list, label, remove parcels; set default phone digits; `/check` |
| Unknown | Anyone else | Gets `NOT_ALLOWED` showing their numeric Telegram ID (so they can send it to the admin). Nothing else. |

Rules:
- Authorization is checked for **every** update before any handler runs (a gate handler in group `-1`).
- `/revoke` sets `is_allowed=0`. The revoked user's parcels stay in the DB but are **not polled** and they get `NOT_ALLOWED` on any message. The admin cannot be revoked.
- On every authorized update, the user's display name (`full_name`) is refreshed in the DB.
- When the admin allows someone, the bot tries to send them `ALLOWED_NOTICE`. If Telegram refuses (they never pressed Start), ignore silently.

## 4. Bot UX

All replies use `parse_mode=HTML`, link previews disabled. Every dynamic value inserted into a message is escaped with `html.escape`. Static strings in §17 are already HTML-safe (e.g. `J&amp;T`).

### 4.1 Commands

| Command | Arguments | Behaviour |
|---|---|---|
| `/start` | – | `WELCOME` (with first name) followed by `HELP`. |
| `/help` | – | `HELP`. |
| `/track` | `<code> [last4]` | Add a parcel (§4.3). Code may contain spaces/dashes (`/track SPXVN 0533 8454 932C`); if the last arg is exactly 4 digits and there are ≥2 args, it is the phone override. No args → `USAGE_TRACK`. |
| *(plain text)* | – | Routed per §4.2. |
| `/list` | – | Active parcels plus terminal parcels updated within `DELIVERED_VISIBLE_FOR` (3 days), numbered 1..n in `created_at` order. Empty → `LIST_EMPTY`. |
| `/status` | `<ref>` | Full history of one parcel, **newest first**, at most `MAX_EVENTS_IN_HISTORY` (30). `ref` = tracking code or the index shown by `/list`. |
| `/label` | `<ref> [name…]` | Set nickname (trimmed, max `MAX_LABEL_LENGTH` = 40 chars). No name → clear label. |
| `/remove` | `<ref>` | Delete the parcel and its events. |
| `/phone` | `[last4 \| clear]` | No arg → show saved default (or `PHONE_NONE`). 4 digits → save default. `clear` → remove default. Anything else → `INVALID_PHONE`. |
| `/check` | – | Immediately poll **this user's** active parcels, ignoring `next_check_at`. At most once per `CHECK_COOLDOWN` (5 min) per user (in-memory). Replies `CHECK_STARTED`, runs the cycle (updates arrive as normal notifications), then `CHECK_DONE`. |
| `/cancel` | – | Clear a pending J&T phone question → `CANCELLED`; nothing pending → `NOTHING_TO_CANCEL`. |
| `/allow` *(admin)* | `<telegram_id> [name…]` | Upsert user with `is_allowed=1`; reply `ALLOWED`; try to DM `ALLOWED_NOTICE`. |
| `/revoke` *(admin)* | `<telegram_id>` | `is_allowed=0`; reply `REVOKED`. Admin id → `CANNOT_REVOKE_ADMIN`. |
| `/users` *(admin)* | – | All users with role and active parcel count. |
| `/health` *(admin)* | – | Last poll time and last `PollReport`, active parcel count, user count. |
| unknown `/command` | – | `UNKNOWN_COMMAND`. |

Commands advertised via `set_my_commands` (Vietnamese descriptions, §9.12): start, help, track, list, status, label, remove, phone, check, cancel. Admin commands are not advertised.

### 4.2 Plain-text routing

`route_text(text, has_pending)`:
1. If a J&T phone question is pending **and** the stripped text is exactly 4 digits → `phone_for_pending`.
2. Else extract tracking codes from the text (`extract_codes`). If ≥1 → `codes` (a pending question, if any, is discarded).
3. Else, if pending → reply `INVALID_PHONE` (keep pending). If not pending → `UNKNOWN_CODE`.

With `codes`:
- **One code** → same as `/track <code>`.
- **Several codes** → add each. SPX codes and J&T codes that can use the user's default phone are added normally (one reply each). J&T codes with no phone available are not added; list them once in `NEEDS_PHONE_MULTI`. No pending question is created for multi-code messages.

### 4.3 Adding a parcel (`ParcelService.add`)

1. Normalize the code (§5.3). Unknown carrier → `invalid_code`.
2. Carrier needs phone (J&T):
   - explicit `last4` argument wins; must pass `is_valid_last4` else `invalid_phone`;
   - else user's `default_phone_last4`;
   - else → `needs_phone` (nothing stored). The handler stores `context.user_data["pending_jt"] = code` and replies `ASK_PHONE`. The next 4-digit message completes the add with that phone.
3. Same user already tracks `(carrier, code)` → `duplicate`.
4. User already has `max_parcels_per_user` (30) **active** parcels → `limit`.
5. Insert parcel: `state=pending`, `next_check_at = now + poll_interval`.
6. Fetch once, immediately:
   - **found** → insert all events silently (no per-event notification), set state (`delivered` / `returned` / `in_transit`), reply `ADDED_FOUND` (latest event text + time) or `ADDED_DELIVERED`.
   - **not found** → stays `pending`, reply `ADDED_PENDING` (+ `ADDED_PENDING_JT_HINT` for J&T).
   - **CarrierError** → record failure (backoff §6.4), reply `ADDED_ERROR`.

Different users may track the same code; each gets their own parcel row. The poller de-duplicates network requests (§6.2).

## 5. Carriers

### 5.1 SPX Express Vietnam

Live probe from this PC on 2026-09-11 (by `agy`):

| Item | Value | Confidence |
|---|---|---|
| Endpoint | `GET https://spx.vn/api/v2/fleet_order/tracking/search?sls_tracking_number=<CODE>` | Verified (HTTP 200) |
| Auth / captcha / signature | None observed | Verified for a fake code only |
| Response envelope | `{"retcode": 0, "message": "", "data": {…}}`; fake code → `data: {}` | Verified |
| Event list shape | **Unknown.** Hypothesis from the Malaysia sibling endpoint: a list of events under `data` with a Unix timestamp, message text, and a status code | Unverified — confirmed by Prompt 2 |
| Delivered / returned markers | Unknown — confirmed by Prompt 2 | Unverified |

Tracking code format: `SPXVN` + 8–16 uppercase alphanumerics (observed examples have 11–14, e.g. `SPXVN05338454932C`).

### 5.2 J&T Express Vietnam

| Item | Value | Confidence |
|---|---|---|
| Tracking page | `https://jtexpress.vn/vi/tracking` | Verified |
| Lookup | Server-rendered HTML. The page's form is `GET https://jtexpress.vn/tracking` with `type=track` and `billcode=<CODE>`; phone digits parameter believed to be `cellphone=<LAST4>` | Form verified; **how the phone digits are actually submitted is unverified** (the hidden `cellphone` input is commented out in the HTML and a separate `tracking_cellphone.js` + verify modal exist) |
| Not-found marker | Text `Không tìm thấy dữ liệu về vận đơn` and/or an `.empty-vandon` block | Verified for a fake code |
| Result markup | Believed to be inside `.result-tracking` | Unverified for real data — confirmed by Prompt 2 |
| Captcha / CSRF / signature on GET | None observed | Verified for fake code |
| Requires last 4 digits of recipient phone | Yes (page asks for it) | Verified via public sources |

Tracking code format: exactly 12 digits (e.g. `841000072647`).

### 5.3 Code normalization and detection

- `normalize_code(raw)`: uppercase; remove all whitespace, `-`, `.`; strip surrounding punctuation `,;:()[]<>"'`.
- `detect_carrier(code)` on a normalized code:
  - `^SPXVN[0-9A-Z]{8,16}$` → `"spx"`
  - `^\d{12}$` → `"jt"`
  - otherwise `None`.
- `extract_codes(text)`: uppercase the text, find `SPXVN[0-9A-Z]{8,16}` and `(?<!\d)\d{12}(?!\d)` matches, return them in order of appearance, de-duplicated. No space-joining inside free text.
- `is_valid_last4(s)`: `^\d{4}$`.

If Prompt 2 observes formats that contradict these patterns, update this section and `tracking_codes.py` together.

### 5.4 Fetch contract (both carriers)

- One shared `httpx.AsyncClient` from `make_http_client(settings)`: timeout `HTTP_TIMEOUT_SECONDS`, `follow_redirects=True`, static headers `DEFAULT_HEADERS` (a normal desktop Chrome `User-Agent`, `Accept-Language: vi-VN,vi;q=0.9,en;q=0.8`). **No User-Agent rotation, no evasion techniques.** Carrier traffic never goes through `TELEGRAM_PROXY_URL` (carriers need the Vietnamese home IP).
- Error mapping → `CarrierError(carrier, reason, detail)`:
  - `httpx.TimeoutException`, `httpx.TransportError` → `network`
  - HTTP 403 or 429, or a captcha / JS-challenge page → `blocked`
  - any other non-200 → `http_status`
  - unparseable body, unexpected structure → `parse`
- "Not found" is **not** an error: return `TrackingResult(found=False)`.
- Event times are carrier-local (Asia/Ho_Chi_Minh) and must become timezone-aware datetimes.
- Events are returned **ascending by time** (stable for equal timestamps).
- `delivered` / `returned` flags come from marker constants in each carrier module, filled from the real fixtures.

### 5.5 Politeness

- Poll interval default 20 min, minimum 5 min.
- Requests to the same carrier are sequential with `REQUEST_DELAY_SECONDS` (3 s) + random 0–`JITTER_SECONDS` (2 s) between them. SPX and J&T are polled concurrently with each other.
- Identical `(carrier, code, last4)` across users → one request per cycle.
- Terminal parcels are never polled.

## 6. Polling and notifications

### 6.1 Schedule

- Job `poll` runs every `POLL_INTERVAL_MINUTES`, first run 30 s after start (this is the catch-up after the PC was off or asleep).
- `Poller.run_cycle` is guarded by an `asyncio.Lock`. Scheduled job: if locked, return `PollReport(skipped=True)` immediately. `/check`: `wait=True` (queues behind the running cycle).

### 6.2 Cycle algorithm

```
now = clock()
parcels = repo.due_parcels(now)                    # active, owner allowed, next_check_at <= now
          or repo.active_parcels_for_user(uid)     # when only_user_id is given
groups  = group parcels by (carrier, tracking_number, phone_last4)
for each carrier concurrently:
    for i, group in enumerate(groups of this carrier):
        if i > 0: await sleep(REQUEST_DELAY_SECONDS + rand() * JITTER_SECONDS)
        try: result = await carrier.fetch(http, code, last4)
        except CarrierError as err: handle_failure(each parcel in group, err); continue
        for parcel in group: handle_result(parcel, result)
after all carriers:
    stale check, carrier alerts, purge, save meta "last_poll_report"
```

### 6.3 Handling a result for one parcel

1. **found**
   - `new = repo.insert_events(parcel.id, result.events)` (only events whose key is new).
   - `state = delivered if result.delivered else returned if result.returned else in_transit`.
   - `repo.record_check_success(...)`: `last_status_text` = latest event description, `last_event_at` = latest event time, `consecutive_failures=0`, `next_check_at = now + interval`, `delivered_at` = latest event time when newly delivered.
   - If `new` is non-empty → send **one message per parcel** built by `format_event_update(parcel, new, tz, delivered=…, returned=…)`; the delivered/returned footer is included only when the state changes in this cycle.
2. **not found**
   - Parcel already has stored events → treat as `CarrierError(reason="parse", detail="events disappeared")` (§6.4). Never delete events.
   - Else if `now - created_at > PENDING_EXPIRY` (7 days) → state `expired`, send `EXPIRED`.
   - Else → `record_check_success(state="pending", …)`; no message.
3. **Stale** — after processing, any `in_transit` parcel in this cycle with `last_event_at < now - STALE_AFTER` (30 days) → state `stale`, send `STALE`.

### 6.4 Failures and backoff

- `n = repo.record_check_failure(parcel.id, next_check_at=…, now=now)` where `next_check_at = now + min(interval × 2ⁿ, MAX_BACKOFF)` using the **new** failure count `n` (`MAX_BACKOFF` = 6 h).
- Count failures per carrier in `PollReport.failures`.
- **Carrier alert** to the admin (`ALERT_CARRIER`) when, in one cycle, any parcel of that carrier reaches exactly `FAILURE_ALERT_THRESHOLD` (5) consecutive failures, **or** every fetch for that carrier failed and there were ≥3 fetches. At most one alert per carrier per `ALERT_COOLDOWN` (6 h), stored in meta key `alert:<carrier>` (ISO time).
- Users are **not** told about transient failures.

### 6.5 Notification delivery

- Quiet hours (`QUIET_HOURS`, default `22-7`, local time, wraps midnight): messages are still sent immediately but with `disable_notification=True` (silent). Outside quiet hours: normal.
- A Telegram send failure is logged and swallowed; stored events are **not** rolled back (prevents re-notification loops; a lost message is acceptable).
- `Forbidden` (user blocked the bot) → log at INFO, continue.
- Updates show at most `MAX_EVENTS_IN_UPDATE` (10) newest new events, chronological, preceded by `UPDATE_MORE` when more were skipped.
- All messages pass through `truncate_message` (limit `TELEGRAM_TEXT_LIMIT` = 4000 chars, cut at a line break, append `…`).

### 6.6 Housekeeping (every cycle)

- `repo.delete_terminal_before(now - PURGE_AFTER)` (30 days) deletes terminal parcels (and events via cascade) whose `updated_at` is older.
- `meta["last_poll_report"] = report.to_json()`; `meta["last_poll_at"] = finished_at ISO`.

## 7. Data model (SQLite)

File `DB_PATH` (default `data/bot.sqlite3`). Connection pragmas on open: `journal_mode=WAL`, `foreign_keys=ON`, `busy_timeout=5000`. Schema version in `PRAGMA user_version`. All timestamps stored as ISO-8601 **UTC** strings (`2026-09-11T10:33:01+00:00`) and returned as aware `datetime` in UTC.

```sql
-- migration 1
CREATE TABLE users (
  telegram_id INTEGER PRIMARY KEY,
  name TEXT,
  default_phone_last4 TEXT CHECK (default_phone_last4 IS NULL OR default_phone_last4 GLOB '[0-9][0-9][0-9][0-9]'),
  is_admin INTEGER NOT NULL DEFAULT 0,
  is_allowed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE parcels (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
  carrier TEXT NOT NULL CHECK (carrier IN ('spx', 'jt')),
  tracking_number TEXT NOT NULL,
  phone_last4 TEXT CHECK (phone_last4 IS NULL OR phone_last4 GLOB '[0-9][0-9][0-9][0-9]'),
  label TEXT,
  state TEXT NOT NULL DEFAULT 'pending'
    CHECK (state IN ('pending', 'in_transit', 'delivered', 'returned', 'expired', 'stale')),
  last_status_text TEXT,
  last_event_at TEXT,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  next_check_at TEXT NOT NULL,
  delivered_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (user_id, carrier, tracking_number)
);
CREATE INDEX idx_parcels_due ON parcels (state, next_check_at);

CREATE TABLE events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  parcel_id INTEGER NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
  event_key TEXT NOT NULL,
  event_time TEXT NOT NULL,
  description TEXT NOT NULL,
  location TEXT,
  raw_status TEXT,
  created_at TEXT NOT NULL,
  UNIQUE (parcel_id, event_key)
);

CREATE TABLE meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
```

States: active = `pending`, `in_transit`; terminal = `delivered`, `returned`, `expired`, `stale`.

`parcels.phone_last4` stores the digits **actually used** for the parcel (override or the user's default at add time), so later changes to the default do not affect existing parcels.

**Event key**: first 16 hex chars of SHA-1 over `"{utc_iso_seconds}|{norm(description)}|{norm(location or '')}"`, where `norm` = collapse whitespace, strip, `casefold()`.

## 8. Architecture

```
Telegram ⇄ python-telegram-bot (long polling, JobQueue)
              │
     bot/ (handlers, auth gate, notifier)      ← thin: parse input, call services, send text
              │
     services/ (ParcelService, Poller, formatting)  ← all business rules, unit-tested with fakes
              │                     │
     db/ Repository (aiosqlite)   carriers/ (SPX JSON, J&T HTML) ⇄ httpx ⇄ spx.vn / jtexpress.vn
```

### 8.1 Repository layout

```
vn-parcel-bot/
├─ BUILD_PLAN.md                spec + build prompts (this document)
├─ README.md                    setup, operations, troubleshooting
├─ pyproject.toml
├─ requirements.lock.txt        pip freeze of the working environment
├─ .env.example
├─ .gitignore
├─ src/vn_parcel_bot/
│  ├─ __init__.py               __version__
│  ├─ __main__.py               main(): python -m vn_parcel_bot
│  ├─ config.py                 Settings, ConfigError
│  ├─ constants.py              policy constants (§10.2)
│  ├─ logging_setup.py          setup_logging, RedactTokenFilter
│  ├─ single_instance.py        SingleInstanceLock, SingleInstanceError
│  ├─ texts.py                  all user-facing strings (§17)
│  ├─ tracking_codes.py         normalize/detect/extract codes
│  ├─ carriers/
│  │  ├─ __init__.py            CARRIERS registry, get_carrier
│  │  ├─ models.py              TrackingEvent, TrackingResult, CarrierError, Carrier protocol
│  │  ├─ http.py                DEFAULT_HEADERS, make_http_client
│  │  ├─ spx.py                 parse_spx_response, SpxCarrier
│  │  └─ jt.py                  parse_jt_html, JtCarrier
│  ├─ db/
│  │  ├─ __init__.py
│  │  ├─ schema.py              SCHEMA_VERSION, MIGRATIONS, migrate
│  │  └─ repo.py                User, Parcel, Repository, DuplicateParcelError
│  ├─ services/
│  │  ├─ __init__.py
│  │  ├─ formatting.py          pure message builders
│  │  ├─ parcels.py             AddOutcome, ParcelService
│  │  └─ poller.py              Notifier protocol, PollReport, Poller
│  └─ bot/
│     ├─ __init__.py
│     ├─ deps.py                Deps, get_deps
│     ├─ app.py                 build_application, poll_job, on_error
│     ├─ auth.py                is_authorized, gate, admin_only
│     ├─ commands.py            BOT_COMMANDS
│     ├─ notifier.py            TelegramNotifier
│     ├─ parsing.py             parse_track_args, parse_ref_and_text, TextRoute, route_text
│     ├─ handlers_user.py
│     └─ handlers_admin.py
├─ scripts/
│  ├─ probe_carriers.py         live probe → tests/fixtures/_raw/
│  ├─ dev_replay_last_event.py  dev tool to re-trigger a notification
│  ├─ run-bot.ps1               foreground run
│  ├─ install-task.ps1          Task Scheduler (start at logon)
│  └─ uninstall-task.ps1
├─ tests/
│  ├─ conftest.py
│  ├─ fakes.py                  FakeCarrier, FakeNotifier, FakeClock
│  ├─ fixtures/
│  │  ├─ FIXTURES.md            observed request/response facts
│  │  ├─ spx/                   in_transit.json, delivered.json, not_found.json [, returned.json]
│  │  ├─ jt/                    in_transit.html, delivered.html, not_found.html [, returned.html]
│  │  └─ _raw/                  unsanitized captures (gitignored)
│  └─ test_*.py
├─ data/                        runtime DB + lock (gitignored)
└─ logs/                        rotating logs (gitignored)
```

## 9. Interface contract

Every name below is fixed. Later prompts rely on them exactly.

### 9.1 `config.py`

```python
class ConfigError(Exception): ...

@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    admin_telegram_id: int
    poll_interval_minutes: int = 20            # 5..240
    request_delay_seconds: float = 3.0         # 0..60
    http_timeout_seconds: float = 15.0         # >0..120
    db_path: Path = Path("data/bot.sqlite3")
    log_dir: Path = Path("logs")
    log_level: str = "INFO"                    # DEBUG|INFO|WARNING|ERROR
    timezone: str = "Asia/Ho_Chi_Minh"
    quiet_hours: tuple[int, int] | None = (22, 7)
    max_parcels_per_user: int = 30             # 1..200
    telegram_proxy_url: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Settings": ...
    @property
    def tz(self) -> ZoneInfo: ...
    @property
    def poll_interval(self) -> timedelta: ...
```

`from_env` collects **all** problems and raises one `ConfigError` listing them. Empty string = unset.

### 9.2 `constants.py`

```python
PENDING_EXPIRY = timedelta(days=7)
STALE_AFTER = timedelta(days=30)
DELIVERED_VISIBLE_FOR = timedelta(days=3)
PURGE_AFTER = timedelta(days=30)
MAX_BACKOFF = timedelta(hours=6)
FAILURE_ALERT_THRESHOLD = 5
CARRIER_ALL_FAILED_MIN_FETCHES = 3
ALERT_COOLDOWN = timedelta(hours=6)
ERROR_ALERT_COOLDOWN = timedelta(minutes=30)
CHECK_COOLDOWN = timedelta(minutes=5)
JITTER_SECONDS = 2.0
FIRST_POLL_DELAY_SECONDS = 30
MAX_LABEL_LENGTH = 40
MAX_EVENTS_IN_UPDATE = 10
MAX_EVENTS_IN_HISTORY = 30
TELEGRAM_TEXT_LIMIT = 4000
```

### 9.3 `logging_setup.py`

```python
class RedactTokenFilter(logging.Filter):
    def __init__(self, secret: str) -> None: ...
    def filter(self, record: logging.LogRecord) -> bool: ...   # replaces secret in msg/args with "***"

def setup_logging(settings: Settings) -> None: ...
```

- Root level = `settings.log_level`. Handlers: `RotatingFileHandler(log_dir/"bot.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8")` and a `StreamHandler` **only if `sys.stderr` is not None** (it is `None` under `pythonw.exe`).
- Format: `%(asctime)s %(levelname)s %(name)s: %(message)s`.
- `httpx` and `httpcore` loggers at `WARNING` (they log full Telegram URLs, which contain the token).
- `RedactTokenFilter(settings.telegram_bot_token)` attached to both handlers.

### 9.4 `single_instance.py`

```python
class SingleInstanceError(RuntimeError): ...

class SingleInstanceLock:
    def __init__(self, path: Path) -> None: ...
    def __enter__(self) -> "SingleInstanceLock": ...   # creates parent dir; msvcrt.locking(LK_NBLCK, 1) → SingleInstanceError if held
    def __exit__(self, *exc) -> None: ...              # unlock + close
```

### 9.5 `tracking_codes.py`

```python
CarrierCode = Literal["spx", "jt"]
def normalize_code(raw: str) -> str: ...
def detect_carrier(code: str) -> CarrierCode | None: ...
def extract_codes(text: str) -> list[str]: ...
def is_valid_last4(value: str) -> bool: ...
def mask_code(code: str) -> str: ...        # code[:5] + "…" + code[-3:], used in logs
```

### 9.6 `carriers/models.py`

```python
ErrorReason = Literal["network", "blocked", "http_status", "parse"]

@dataclass(frozen=True)
class TrackingEvent:
    time: datetime                 # must be timezone-aware, else ValueError
    description: str
    location: str | None = None
    raw_status: str | None = None
    @property
    def key(self) -> str: ...      # §7 event key

@dataclass(frozen=True)
class TrackingResult:
    carrier: CarrierCode
    tracking_number: str
    found: bool
    events: tuple[TrackingEvent, ...] = ()   # __post_init__ stores a stable sort ascending by time
    delivered: bool = False
    returned: bool = False
    @property
    def latest(self) -> TrackingEvent | None: ...

class CarrierError(Exception):
    def __init__(self, carrier: CarrierCode, reason: ErrorReason, detail: str = "") -> None: ...
    carrier: CarrierCode
    reason: ErrorReason
    detail: str
    # str(err) == f"{carrier}:{reason}: {detail}"

class Carrier(Protocol):
    code: CarrierCode
    display_name: str          # "SPX" / "J&T" (plain text; formatting escapes)
    needs_phone: bool
    async def fetch(self, http: httpx.AsyncClient, tracking_number: str,
                    phone_last4: str | None = None) -> TrackingResult: ...
```

### 9.7 `carriers/http.py`, `spx.py`, `jt.py`, `__init__.py`

```python
# http.py
DEFAULT_HEADERS: dict[str, str]
def make_http_client(settings: Settings) -> httpx.AsyncClient: ...

# spx.py
SPX_TRACKING_URL = "https://spx.vn/api/v2/fleet_order/tracking/search"
DELIVERED_MARKERS: tuple[str, ...]     # from fixtures
RETURNED_MARKERS: tuple[str, ...]      # from fixtures
def parse_spx_response(payload: dict, tracking_number: str) -> TrackingResult: ...
class SpxCarrier:  code = "spx"; display_name = "SPX"; needs_phone = False

# jt.py
JT_TRACKING_URL = "https://jtexpress.vn/tracking"      # adjust only if Prompt 2 proves otherwise
NOT_FOUND_MARKER = "Không tìm thấy dữ liệu"
DELIVERED_MARKERS: tuple[str, ...]
RETURNED_MARKERS: tuple[str, ...]
def parse_jt_html(html: str, tracking_number: str) -> TrackingResult: ...
class JtCarrier:   code = "jt"; display_name = "J&T"; needs_phone = True
                   # fetch raises ValueError if phone_last4 is None

# __init__.py
CARRIERS: dict[CarrierCode, Carrier]   # {"spx": SpxCarrier(), "jt": JtCarrier()}
def get_carrier(code: CarrierCode) -> Carrier: ...
```

### 9.8 `db/schema.py`, `db/repo.py`

```python
# schema.py
SCHEMA_VERSION = 1
MIGRATIONS: list[str]                              # index i = SQL script bringing version i → i+1
async def migrate(conn: aiosqlite.Connection) -> None: ...

# repo.py
ParcelState = Literal["pending", "in_transit", "delivered", "returned", "expired", "stale"]
ACTIVE_STATES: tuple[ParcelState, ...] = ("pending", "in_transit")
TERMINAL_STATES: tuple[ParcelState, ...] = ("delivered", "returned", "expired", "stale")

class DuplicateParcelError(Exception): ...

@dataclass(frozen=True)
class User:
    telegram_id: int
    name: str | None
    default_phone_last4: str | None
    is_admin: bool
    is_allowed: bool
    created_at: datetime

@dataclass(frozen=True)
class Parcel:
    id: int
    user_id: int
    carrier: CarrierCode
    tracking_number: str
    phone_last4: str | None
    label: str | None
    state: ParcelState
    last_status_text: str | None
    last_event_at: datetime | None
    consecutive_failures: int
    next_check_at: datetime
    delivered_at: datetime | None
    created_at: datetime
    updated_at: datetime
    @property
    def is_active(self) -> bool: ...

class Repository:
    @classmethod
    async def open(cls, db_path: Path | str) -> "Repository": ...     # creates parent dir, pragmas, migrate
    async def close(self) -> None: ...
    # users
    async def upsert_user(self, telegram_id: int, *, now: datetime, name: str | None = None,
                          is_allowed: bool | None = None, is_admin: bool | None = None) -> User: ...
    async def get_user(self, telegram_id: int) -> User | None: ...
    async def list_users(self) -> list[User]: ...
    async def set_default_phone(self, telegram_id: int, last4: str | None) -> None: ...
    # parcels
    async def add_parcel(self, *, user_id: int, carrier: CarrierCode, tracking_number: str,
                         phone_last4: str | None, now: datetime, next_check_at: datetime) -> Parcel: ...
    async def get_parcel(self, parcel_id: int) -> Parcel | None: ...
    async def find_parcel(self, user_id: int, tracking_number: str) -> Parcel | None: ...
    async def list_parcels(self, user_id: int, *, terminal_since: datetime) -> list[Parcel]: ...  # active + terminal with updated_at >= terminal_since; ORDER BY created_at, id
    async def count_active_parcels(self, user_id: int) -> int: ...
    async def active_parcels_for_user(self, user_id: int) -> list[Parcel]: ...
    async def due_parcels(self, now: datetime) -> list[Parcel]: ...   # active, owner is_allowed=1, next_check_at <= now; ORDER BY next_check_at, id
    async def set_label(self, parcel_id: int, label: str | None, now: datetime) -> None: ...
    async def delete_parcel(self, parcel_id: int) -> None: ...
    async def record_check_success(self, parcel_id: int, *, state: ParcelState,
                                   last_status_text: str | None, last_event_at: datetime | None,
                                   next_check_at: datetime, now: datetime,
                                   delivered_at: datetime | None = None) -> None: ...   # resets consecutive_failures; None for last_* / delivered_at keeps existing value
    async def record_check_failure(self, parcel_id: int, *, next_check_at: datetime,
                                   now: datetime) -> int: ...                          # returns new consecutive_failures
    async def set_state(self, parcel_id: int, state: ParcelState, now: datetime) -> None: ...
    async def delete_terminal_before(self, cutoff: datetime) -> int: ...
    async def count_all_active(self) -> int: ...
    # events
    async def insert_events(self, parcel_id: int, events: Sequence[TrackingEvent],
                            now: datetime) -> list[TrackingEvent]: ...   # returns newly inserted, ascending
    async def list_events(self, parcel_id: int, limit: int) -> list[TrackingEvent]: ...  # the `limit` most recent, returned ascending
    async def count_events(self, parcel_id: int) -> int: ...
    # meta
    async def get_meta(self, key: str) -> str | None: ...
    async def set_meta(self, key: str, value: str) -> None: ...
```

`add_parcel` raises `DuplicateParcelError` on the UNIQUE constraint.

### 9.9 `services/formatting.py` (pure, no I/O)

```python
def parcel_title(parcel: Parcel) -> str: ...                       # escaped label, else tracking number
def carrier_name(code: CarrierCode) -> str: ...                    # CARRIER_NAMES (HTML-safe)
def format_time(dt: datetime, tz: ZoneInfo) -> str: ...            # TIME_FORMAT in tz
def format_event_update(parcel: Parcel, new_events: Sequence[TrackingEvent], tz: ZoneInfo,
                        *, delivered: bool, returned: bool) -> str: ...
def format_parcel_list(parcels: Sequence[Parcel], tz: ZoneInfo) -> str: ...
def format_history(parcel: Parcel, events: Sequence[TrackingEvent], tz: ZoneInfo) -> str: ...  # newest first
def format_add_outcome(outcome: AddOutcome, tz: ZoneInfo, *, max_parcels: int) -> str: ...
def format_needs_phone_multi(codes: Sequence[str]) -> str: ...
def format_expired(parcel: Parcel) -> str: ...
def format_stale(parcel: Parcel) -> str: ...
def format_carrier_alert(carrier: CarrierCode, count: int, detail: str) -> str: ...
def format_users(users: Sequence[User], active_counts: Mapping[int, int], admin_id: int) -> str: ...
def format_health(last_poll_at: datetime | None, report: dict | None, active: int, users: int,
                  tz: ZoneInfo) -> str: ...
def truncate_message(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> str: ...
```

### 9.10 `services/parcels.py`

```python
AddKind = Literal["added", "needs_phone", "duplicate", "limit", "invalid_code", "invalid_phone"]

@dataclass(frozen=True)
class AddOutcome:
    kind: AddKind
    code: str | None = None                  # normalized code when known
    parcel: Parcel | None = None             # refreshed after the first fetch
    result: TrackingResult | None = None
    error: CarrierError | None = None

class ParcelService:
    def __init__(self, repo: Repository, carriers: Mapping[CarrierCode, Carrier],
                 http: httpx.AsyncClient, settings: Settings,
                 now: Callable[[], datetime]) -> None: ...
    async def add(self, user: User, raw_code: str, phone_last4: str | None = None) -> AddOutcome: ...
    async def list_for(self, user_id: int) -> list[Parcel]: ...
    async def resolve(self, user_id: int, ref: str) -> Parcel | None: ...     # 1-3 digit ref = 1-based index into list_for; else normalized code
    async def remove(self, user_id: int, ref: str) -> Parcel | None: ...      # returns the deleted parcel
    async def rename(self, user_id: int, ref: str, label: str | None) -> Parcel | None: ...
    async def history(self, user_id: int, ref: str) -> tuple[Parcel, list[TrackingEvent]] | None: ...
    async def set_default_phone(self, user_id: int, last4: str | None) -> None: ...  # ValueError if invalid
```

### 9.11 `services/poller.py`

```python
class Notifier(Protocol):
    async def send(self, chat_id: int, text: str, *, silent: bool = False) -> None: ...

@dataclass
class PollReport:
    started_at: datetime
    finished_at: datetime
    skipped: bool = False
    parcels_checked: int = 0
    fetches: int = 0
    new_events: int = 0
    messages_sent: int = 0
    failures: dict[str, int] = field(default_factory=dict)
    def to_json(self) -> str: ...

class Poller:
    def __init__(self, repo: Repository, carriers: Mapping[CarrierCode, Carrier],
                 http: httpx.AsyncClient, notifier: Notifier, settings: Settings,
                 now: Callable[[], datetime],
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 rand: Callable[[], float] = random.random) -> None: ...
    async def run_cycle(self, *, only_user_id: int | None = None, wait: bool = False) -> PollReport: ...
    def is_quiet(self, at: datetime) -> bool: ...
```

### 9.12 `bot/`

```python
# parsing.py
def parse_track_args(args: Sequence[str]) -> tuple[str, str | None] | None: ...
def parse_ref_and_text(args: Sequence[str]) -> tuple[str, str | None] | None: ...
@dataclass(frozen=True)
class TextRoute:
    kind: Literal["phone_for_pending", "codes", "invalid_phone", "unknown"]
    codes: tuple[str, ...] = ()
    last4: str | None = None
def route_text(text: str, has_pending: bool) -> TextRoute: ...

# auth.py
def is_authorized(user: User | None, telegram_id: int, admin_id: int) -> bool: ...
async def gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: ...   # TypeHandler group -1; raises ApplicationHandlerStop
def admin_only(handler): ...                                                      # decorator

# commands.py
BOT_COMMANDS: list[tuple[str, str]]

# notifier.py
class TelegramNotifier:        # implements Notifier
    def __init__(self, bot: Bot) -> None: ...

# deps.py  (separate module so auth/handlers/app can import it without cycles)
@dataclass
class Deps:
    settings: Settings
    repo: Repository
    http: httpx.AsyncClient
    parcels: ParcelService
    poller: Poller
    notifier: TelegramNotifier
def get_deps(context: ContextTypes.DEFAULT_TYPE) -> Deps: ...     # context.bot_data["deps"]

# app.py
def build_application(settings: Settings) -> Application: ...
async def poll_job(context: ContextTypes.DEFAULT_TYPE) -> None: ...
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None: ...

# __main__.py
def main() -> int: ...
```

`BOT_COMMANDS`:
```python
[("start", "Bắt đầu"), ("help", "Hướng dẫn"), ("track", "Theo dõi đơn: /track <mã> [4 số cuối SĐT]"),
 ("list", "Danh sách đơn"), ("status", "Hành trình đơn"), ("label", "Đặt tên cho đơn"),
 ("remove", "Ngừng theo dõi"), ("phone", "4 số cuối SĐT cho đơn J&T"), ("check", "Kiểm tra ngay"),
 ("cancel", "Hủy thao tác")]
```

## 10. Configuration

### 10.1 `.env`

| Variable | Required | Default | Validation |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | – | matches `^\d+:[A-Za-z0-9_-]{30,}$` |
| `ADMIN_TELEGRAM_ID` | yes | – | positive int |
| `POLL_INTERVAL_MINUTES` | no | `20` | int 5..240 |
| `REQUEST_DELAY_SECONDS` | no | `3` | float 0..60 |
| `HTTP_TIMEOUT_SECONDS` | no | `15` | float >0..120 |
| `DB_PATH` | no | `data/bot.sqlite3` | path |
| `LOG_DIR` | no | `logs` | path |
| `LOG_LEVEL` | no | `INFO` | DEBUG/INFO/WARNING/ERROR (case-insensitive, stored upper) |
| `TIMEZONE` | no | `Asia/Ho_Chi_Minh` | loadable by `ZoneInfo` |
| `QUIET_HOURS` | no | `22-7` | `H-H` with 0..23, `H1 != H2`; empty string → disabled |
| `MAX_PARCELS_PER_USER` | no | `30` | int 1..200 |
| `TELEGRAM_PROXY_URL` | no | – | `http://`, `https://`, `socks5://` or `socks5h://` URL |

Note: `QUIET_HOURS` unset → default `(22, 7)`; set to empty → `None`. Relative paths are relative to the working directory (the repo root when run via the scripts).

### 10.2 Policy constants

See §9.2. They are code constants, not env vars.

## 11. Logging, security, privacy

- Never log or print the bot token. Enforced by `httpx`/`httpcore` at WARNING and `RedactTokenFilter`.
- `.env`, `data/`, `logs/`, `tests/fixtures/_raw/`, `probe_codes.local.txt` are gitignored.
- Only the **last 4 digits** of a phone number are stored.
- Committed fixtures are sanitized: names, addresses, full phone numbers, courier names/phones, and the real tracking codes are replaced with fake values (`SPXVN000000000001`, `840000000001`, …).
- Log at INFO: startup/shutdown, each poll cycle summary (counts only), parcel added/removed (masked code: first 5 + `…` + last 3), carrier errors (reason + masked code). Never log message bodies or full tracking histories at INFO.
- Input handling: codes must match strict regexes; labels trimmed and length-limited; everything escaped before sending as HTML.
- The bot ignores non-private chats.

## 12. Runtime on Windows

- Python 3.13 virtualenv at `.venv`. Entry: `.venv\Scripts\python.exe -m vn_parcel_bot` (foreground) or `pythonw.exe` (background, no console).
- **Single instance**: `SingleInstanceLock(db_path.parent / "bot.lock")`. If held → log WARNING "another instance is running" and exit **0** (so Task Scheduler does not restart-loop).
- **Exit codes**: `0` normal / duplicate instance; `2` configuration error or Telegram rejected the token (also written to `logs/startup-error.log`, because `pythonw` has no console); `1` unexpected crash.
- **Telegram `Conflict`** (another process is polling with the same token) → log CRITICAL and stop the application (exit 1).
- **Auto-start**: Task Scheduler task `VN Parcel Bot`, trigger *At log on* of the current user, action `pythonw.exe -m vn_parcel_bot` in the repo root, restart on failure every 1 min (999×), no execution time limit, runs on battery, `MultipleInstances IgnoreNew`. Installed by `scripts/install-task.ps1`.
- **Sleep/off**: no polling while the PC sleeps; the first cycle after wake/start catches up. Recommended: *Sleep = Never* while plugged in.
- **Telegram reachability**: in 2025 Vietnam ordered telecom providers to block Telegram; access may fail on some ISPs. If `api.telegram.org` is unreachable, set `TELEGRAM_PROXY_URL` (e.g. a local VPN client's HTTP/SOCKS proxy). The proxy is used for Telegram only.
- **Time zones**: Windows has no system IANA database; the `tzdata` package is a required dependency.

## 13. Testing strategy

- `pytest` + `pytest-asyncio` (`asyncio_mode=auto`), `respx` for HTTP mocking, `pytest-cov`.
- **No real network in automated tests.** Live checks live only in `scripts/probe_carriers.py` and the manual E2E prompt.
- Carrier parsers are tested against the sanitized **real** fixtures.
- Repository tests use a temp-file SQLite DB (`tmp_path`).
- Services are tested with the real `Repository` plus `tests/fakes.py`:
  - `FakeClock` — `now()` returns a settable aware UTC datetime; `advance(timedelta)`.
  - `FakeCarrier(code, needs_phone)` — `results: dict[tuple[str, str | None], TrackingResult | CarrierError]`, records `calls: list[tuple[str, str | None]]`; raises the error if the mapped value is a `CarrierError`; unknown key → `TrackingResult(found=False)`.
  - `FakeNotifier` — records `sent: list[tuple[int, str, bool]]`; optional `fail_with: Exception | None`.
- Telegram handlers stay thin; their parsing/authorization logic lives in pure functions (`bot/parsing.py`, `bot/auth.py.is_authorized`) that are unit-tested. The handler wiring is verified by a no-network `build_application` smoke test and the manual E2E run.
- Coverage target: ≥ 85 % for `tracking_codes`, `carriers`, `db`, `services`.
- Quality gates on every prompt: `pytest -q` green, `ruff check .` clean, `ruff format --check .` clean.

## 14. Acceptance scenarios (manual E2E)

1. Unknown account sends `/start` → `NOT_ALLOWED` with its numeric ID.
2. Admin `/allow <id> Mẹ` → admin gets `ALLOWED`; the new user gets `ALLOWED_NOTICE`; `/start` now works for them.
3. Paste a real in-transit SPX code → `ADDED_FOUND` with the current status; `/list` shows it with 🚚.
4. Paste a J&T code with no default phone → `ASK_PHONE`; send 4 digits → `ADDED_FOUND` (or `ADDED_PENDING` + hint).
5. `/phone 1234`, then paste another J&T code → added without asking.
6. `/track <jt-code> 5678` → uses 5678 regardless of the default.
7. Paste a message containing one SPX and one J&T code (no default phone) → SPX added; `NEEDS_PHONE_MULTI` lists the J&T code.
8. `scripts/dev_replay_last_event.py <code>` then wait ≤ 1 interval (or `/check`) → exactly one update message containing that event; a second cycle sends nothing.
9. A delivered parcel produces the `UPDATE_DELIVERED` footer once, is no longer polled, stays in `/list` for 3 days.
10. `/label 1 Áo khoác` → `/list` and future updates show "Áo khoác"; `/label 1` clears it.
11. `/status 1` → history newest first; `/remove 1` → `REMOVED`, gone from `/list`.
12. Restart the PC and log in → bot running within 1 min; no duplicate notifications for already-seen events.
13. Disconnect the network for 15 min → no crash, no user messages about errors, recovery after reconnection; after 5 consecutive failures admin gets one `ALERT_CARRIER`.
14. Start a second instance manually → it exits immediately with the "another instance" log line.
15. `Select-String -Path logs\* -Pattern <token>` → no matches.

## 15. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | SPX endpoint needs extra headers/tokens for real data (only a fake code was tested) | Medium | High | Prompt 2 is a hard gate with real codes; if blocked, stop and choose: browser-copied headers, headless browser, or paid aggregator |
| R2 | J&T phone-digit submission differs from the assumed `cellphone` GET param | Medium | High | Prompt 2 inspects `tracking_cellphone.js` and the verify modal and tests with a real code + digits |
| R3 | Carriers change markup/API or add anti-bot | Medium (over months) | High | Parser errors → backoff + admin alert; fixtures make fixes quick; conservative polling |
| R4 | Telegram blocked by the ISP | Medium | High | Pre-flight check; `TELEGRAM_PROXY_URL` |
| R5 | PC off or asleep | High | Low–Medium | Catch-up cycle on start; auto-start task; power settings |
| R6 | Wrong J&T phone digits look like "not found" | Medium | Low | Hint on add; `EXPIRED` after 7 days tells the user to check digits |
| R7 | Token leak via logs or commits | Low | High | httpx log level, redact filter, gitignore, acceptance check 15 |
| R8 | Terms-of-use concerns with automated lookups | Low | Medium | Personal, low-volume, honest client, no evasion, no resale |
| R9 | Duplicate bot instances | Low | Medium | Lock file + `MultipleInstances IgnoreNew` + `Conflict` handling |
| R10 | Timezone errors on Windows | Medium | Low | `tzdata` dependency, aware datetimes enforced by `TrackingEvent` |

## 16. Out of scope for v1 (future ideas)

- Auto-import codes from Gmail (Shopee/TikTok/Lazada emails) or a Shopee account.
- More carriers (GHN, GHTK, Viettel Post, Ninja Van, BEST Express, VNPost).
- Batched J&T lookups (the page accepts up to 10 codes) — only worth it at larger volumes.
- Inline buttons on notifications (remove/label), per-user "milestones only" mode, English UI.
- Group-chat mode, web dashboard, VPS/cloud hosting, DB backups (data is short-lived).
- Paid aggregator fallback (17TRACK/TrackingMore) if direct endpoints become unusable.

---

## 17. Text catalog (`texts.py`)

All messages are sent with `parse_mode=HTML`. `{placeholders}` are filled with **already-escaped** values by `services/formatting.py`. Copy verbatim.

```python
TIME_FORMAT = "%d/%m %H:%M"

CARRIER_NAMES = {"spx": "SPX", "jt": "J&amp;T"}

STATE_EMOJI = {
    "pending": "⏳", "in_transit": "🚚", "delivered": "✅",
    "returned": "↩️", "expired": "⌛", "stale": "⚠️",
}
STATE_TEXT = {
    "pending": "Chưa có thông tin vận chuyển",
    "in_transit": "Đang vận chuyển",
    "delivered": "Đã giao",
    "returned": "Hoàn hàng",
    "expired": "Đã ngừng theo dõi (không có dữ liệu)",
    "stale": "Đã ngừng theo dõi (quá lâu không cập nhật)",
}

WELCOME = (
    "Xin chào {name}! 👋\n"
    "Mình sẽ nhắn cho bạn mỗi khi đơn SPX hoặc J&amp;T có cập nhật mới.\n"
    "Gửi mã vận đơn để bắt đầu."
)
HELP = (
    "<b>📦 Hướng dẫn</b>\n"
    "• Gửi mã vận đơn để theo dõi (SPX: bắt đầu bằng SPXVN · J&amp;T: 12 chữ số)\n"
    "• /track &lt;mã&gt; [4 số cuối SĐT] – theo dõi đơn\n"
    "• /list – các đơn đang theo dõi\n"
    "• /status &lt;mã hoặc số thứ tự&gt; – xem hành trình\n"
    "• /label &lt;mã hoặc số thứ tự&gt; &lt;tên&gt; – đặt tên cho đơn\n"
    "• /remove &lt;mã hoặc số thứ tự&gt; – ngừng theo dõi\n"
    "• /phone &lt;4 số&gt; – lưu 4 số cuối SĐT cho đơn J&amp;T (/phone clear để xóa)\n"
    "• /check – kiểm tra ngay\n"
    "• /cancel – hủy thao tác đang chờ"
)
NOT_ALLOWED = (
    "🔒 Bạn chưa có quyền dùng bot này.\n"
    "Hãy gửi ID sau cho người quản lý: <code>{user_id}</code>"
)
ADMIN_ONLY = "🔒 Lệnh này chỉ dành cho người quản lý."
UNKNOWN_COMMAND = "Mình không hiểu lệnh này. Gõ /help để xem hướng dẫn."
UNKNOWN_CODE = (
    "🤔 Mình không nhận ra mã vận đơn nào.\n"
    "Mã SPX bắt đầu bằng SPXVN, mã J&amp;T gồm 12 chữ số. Gõ /help để xem hướng dẫn."
)
ERROR_GENERIC = "😵 Có lỗi xảy ra, bạn thử lại sau nhé."

USAGE_TRACK = "Cách dùng: /track &lt;mã&gt; [4 số cuối SĐT]"
USAGE_REF = "Cách dùng: /{command} &lt;mã hoặc số thứ tự trong /list&gt;"
USAGE_LABEL = "Cách dùng: /label &lt;mã hoặc số thứ tự&gt; &lt;tên&gt; (bỏ trống tên để xóa)"

ASK_PHONE = (
    "📱 Đơn J&amp;T <code>{code}</code> cần 4 số cuối SĐT người nhận.\n"
    "Gửi 4 số đó, hoặc /cancel để hủy."
)
INVALID_PHONE = "Vui lòng nhập đúng 4 chữ số."
NEEDS_PHONE_MULTI = (
    "📱 Các đơn J&amp;T sau cần 4 số cuối SĐT. "
    "Hãy thêm từng đơn bằng /track &lt;mã&gt; &lt;4 số&gt;:\n{codes}"
)

ADDED_FOUND = "✅ Đã theo dõi <b>{title}</b> · {carrier}\nTrạng thái hiện tại: {status}\n🕒 {time}"
ADDED_DELIVERED = "✅ Đã thêm <b>{title}</b> · {carrier} — đơn này đã giao thành công.\n🕒 {time}"
ADDED_PENDING = (
    "✅ Đã thêm <b>{title}</b> · {carrier}\n"
    "Hiện chưa có thông tin vận chuyển, mình sẽ kiểm tra lại định kỳ."
)
ADDED_PENDING_JT_HINT = "\nNếu vài giờ nữa vẫn chưa có dữ liệu, hãy kiểm tra lại 4 số cuối SĐT."
ADDED_ERROR = (
    "✅ Đã thêm <b>{title}</b> · {carrier}\n"
    "Hiện chưa kết nối được với {carrier}, mình sẽ thử lại sau."
)
DUPLICATE = "Bạn đã theo dõi đơn <code>{code}</code> rồi."
LIMIT_REACHED = "Bạn đang theo dõi tối đa {max} đơn. Hãy /remove bớt đơn cũ nhé."

LIST_HEADER = "<b>📋 Đơn của bạn</b>"
LIST_EMPTY = "Bạn chưa theo dõi đơn nào. Gửi mã vận đơn để bắt đầu."
LIST_ITEM = "{index}. {emoji} <b>{title}</b> · {carrier}\n    {status}{time_suffix}"
LIST_TIME_SUFFIX = " · 🕒 {time}"

HISTORY_HEADER = "<b>📦 {title}</b> · {carrier} · <code>{code}</code>"
HISTORY_EMPTY = "Chưa có thông tin vận chuyển."
PARCEL_NOT_FOUND = "Không tìm thấy đơn <code>{ref}</code> trong danh sách của bạn."

REMOVED = "🗑 Đã ngừng theo dõi <b>{title}</b>."
LABEL_SET = "🏷 Đã đặt tên: <b>{label}</b>"
LABEL_CLEARED = "🏷 Đã xóa tên của đơn <code>{code}</code>."

PHONE_SET = "📱 Đã lưu 4 số cuối mặc định: <code>{last4}</code>"
PHONE_SHOW = "📱 4 số cuối mặc định: <code>{last4}</code>"
PHONE_NONE = "Bạn chưa lưu 4 số cuối nào. Dùng /phone &lt;4 số&gt; để lưu."
PHONE_CLEARED = "📱 Đã xóa 4 số cuối mặc định."

CANCELLED = "Đã hủy."
NOTHING_TO_CANCEL = "Không có thao tác nào đang chờ."

CHECK_TOO_SOON = "⏱ Bạn vừa kiểm tra xong. Thử lại sau {minutes} phút nhé."
CHECK_STARTED = "🔄 Đang kiểm tra các đơn của bạn…"
CHECK_DONE = "✔️ Đã kiểm tra {checked} đơn, có {new_events} cập nhật mới."

UPDATE_HEADER = "📦 <b>{title}</b> · {carrier}"
UPDATE_LINE = "• {time} — {description}"
UPDATE_LOCATION = " ({location})"
UPDATE_MORE = "… và {count} cập nhật trước đó"
UPDATE_DELIVERED = "✅ <b>Đã giao thành công!</b>"
UPDATE_RETURNED = "↩️ <b>Đơn đang được hoàn về người gửi.</b>"

EXPIRED = (
    "⌛ Sau 7 ngày vẫn chưa có dữ liệu cho <code>{code}</code>, mình đã ngừng theo dõi.\n"
    "Hãy kiểm tra lại mã vận đơn (và 4 số cuối SĐT nếu là đơn J&amp;T)."
)
STALE = "⚠️ Đơn <b>{title}</b> không có cập nhật nào trong 30 ngày, mình đã ngừng theo dõi."

USAGE_ALLOW = "Cách dùng: /allow &lt;telegram_id&gt; [tên]"
USAGE_REVOKE = "Cách dùng: /revoke &lt;telegram_id&gt;"
ALLOWED = "✅ Đã cấp quyền cho <code>{user_id}</code>{name_suffix}."
ALLOWED_NOTICE = "🎉 Bạn đã được cấp quyền dùng bot! Gõ /help để xem hướng dẫn."
REVOKED = "🚫 Đã thu hồi quyền của <code>{user_id}</code>."
CANNOT_REVOKE_ADMIN = "Không thể thu hồi quyền của người quản lý."
USERS_HEADER = "<b>👥 Người dùng</b>"
USERS_ITEM = "• <code>{user_id}</code> {name} — {role} · {active} đơn đang theo dõi"
ROLE_ADMIN = "quản lý"
ROLE_MEMBER = "thành viên"
ROLE_BLOCKED = "đã khóa"

HEALTH = (
    "<b>🩺 Tình trạng</b>\n"
    "Lần kiểm tra gần nhất: {last_poll}\n"
    "Đơn đang theo dõi: {active}\n"
    "Người dùng: {users}\n"
    "Chu kỳ gần nhất: {fetches} lượt tra cứu, {new_events} cập nhật mới, lỗi: {failures}"
)
HEALTH_NEVER = "chưa chạy"

ALERT_CARRIER = (
    "⚠️ <b>{carrier}</b>: {count} lỗi liên tiếp khi tra cứu.\n"
    "Có thể trang tra cứu đã thay đổi hoặc đang chặn. Lỗi gần nhất: <code>{detail}</code>"
)
ALERT_ERROR = "⚠️ Bot gặp lỗi: <code>{detail}</code>"
```
