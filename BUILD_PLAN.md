# vn-parcel-bot — Build Plan

Version 1.0 · 2026-09-11 · Status: draft for review

One self-contained document for building a Telegram bot that notifies a small allowlisted group about **SPX Express Vietnam** and **J&T Express Vietnam** parcels. Hand it to any coding agent (Antigravity `agy`, Claude Code, Gemini CLI, Codex, …) running inside the repository.

| Part | Contents | Used by |
|---|---|---|
| 1. Guide | Progress tracker, how to run prompts, standing rules | You and agents |
| 2. Specification (§1–§17) | What to build — the binding source of truth | Agents: read fully before coding |
| 3. Prompts (0–13) | Step-by-step build prompts | Agents, one prompt per run |
| 4. Appendices (A–D) | Maintenance prompts, troubleshooting, spec coverage map | You and agents |

Citation conventions used everywhere in this file: `§N` = a section of Part 2; `Prompt N` = Part 3; `Appendix X` = Part 4. If code and Part 2 disagree, Part 2 wins; if Part 2 is wrong, fix Part 2 first (in the same commit), then the code.

- Repo: `C:\Users\hozkg\projects\vn-parcel-bot` — this file lives at its root as `BUILD_PLAN.md`
- Shell: Windows PowerShell 5.1 (no `&&`; use `;` or `if ($?) { … }`)
- Python: 3.13 in `.venv`

---

# Part 1 — Guide

## Progress

| # | Prompt | Needs from you | Done |
|---|---|---|---|
| 0 | Pre-flight (you, ~20 min) | BotFather, Telegram ID, real codes | [ ] |
| 1 | Scaffold, settings, logging | – | [ ] |
| 2 | HTTP client, live probe, real fixtures — **GATE** | `.env`, `probe_codes.local.txt` | [ ] |
| 3 | Tracking codes and tracking models | – | [ ] |
| 4 | SPX carrier | – | [ ] |
| 5 | J&T carrier and carrier registry | – | [ ] |
| 6 | Database schema and repository | – | [ ] |
| 7 | Texts and message formatting | – | [ ] |
| 8 | Parcel service | – | [ ] |
| 9 | Poller | – | [ ] |
| 10 | Telegram bot layer and entry point | – | [ ] |
| 11 | Live end-to-end run (interactive) | Your phone + family account | [ ] |
| 12 | Windows auto-start and README | – | [ ] |
| 13 | Hardening drills and final review | – | [ ] |

Run prompts **in order**. Do not start a prompt until the previous one is committed and its "Done when" checks pass.

---

## How to run a prompt

### With `agy` (Antigravity CLI)

Non-interactive (good for Prompts 1, 3–10, 12):

```powershell
Set-Location $HOME\projects\vn-parcel-bot
agy --dangerously-skip-permissions --model claude-opus-4-6-thinking --print-timeout 45m --output-format json `
  -p "Read BUILD_PLAN.md: 'Standing rules' in Part 1, all of Part 2 (Specification), and 'Prompt 3' in Part 3. Execute Prompt 3 only. Stop when its 'Done when' checks pass and report."
```

Interactive (needed for Prompts 2, 11, 13 because they involve you):

```powershell
agy --dangerously-skip-permissions --model claude-opus-4-6-thinking `
  -i "Read BUILD_PLAN.md: 'Standing rules' in Part 1, all of Part 2 (Specification), and 'Prompt 11' in Part 3. Execute Prompt 11 only."
```

Notes:
- `--print-timeout` defaults to 5 min; coding prompts need 30–45 min.
- Swap `--model` for `gemini-3.1-pro-high` if you prefer; use the same model for a whole prompt.
- Inspect what `agy` did: `~\.gemini\antigravity-cli\brain\<conversation_id>\.system_generated\logs\transcript.jsonl`.
- Resume a stalled run: `agy --conversation <conversation_id> ...`.

### With Claude Code

```powershell
Set-Location $HOME\projects\vn-parcel-bot
claude "Read BUILD_PLAN.md: 'Standing rules' in Part 1, all of Part 2 (Specification), and 'Prompt 3' in Part 3. Execute Prompt 3 only."
```

### After each prompt (you, 2 min)

1. `git log --oneline -3` — the prompt's commit exists.
2. `.\.venv\Scripts\python -m pytest -q` — green.
3. Skim `git show --stat HEAD` — only expected files changed.
4. Tick the row in **Progress** (or let the agent do it).

---

## Standing rules (apply to every prompt)

1. **Read Part 2 (Specification) completely before writing code.** Names, signatures, constants, SQL, and texts in the spec are binding. If the spec is ambiguous or wrong, **stop and report** instead of guessing; if a prompt explicitly allows a spec update, edit Part 2 of `BUILD_PLAN.md` in the same commit.
2. **Stay in scope.** Only create/modify the files listed in the prompt (plus `BUILD_PLAN.md` for progress ticks and permitted spec updates). Do not refactor earlier prompts' public interfaces.
3. **TDD.** Write the listed tests first, run them and see them fail for the right reason, implement, run until green.
4. **No real network in `tests/`.** Use `respx` for HTTP and fakes from `tests/fakes.py`. Live traffic only in `scripts/` and in prompts that say so.
5. **Quality gates before committing** (all must pass):
   ```powershell
   .\.venv\Scripts\python -m pytest -q
   .\.venv\Scripts\python -m ruff check .
   .\.venv\Scripts\python -m ruff format --check .
   ```
6. **Secrets.** Never print, log, or commit the bot token, `.env`, real tracking codes, real names/addresses/phones. Do not `Get-Content .env` into the transcript.
7. **Windows.** Use PowerShell 5.1 syntax. Use `.\.venv\Scripts\python -m <tool>` rather than bare `pytest`/`ruff`.
8. **Style.** Type hints everywhere; `from __future__ import annotations` not needed (3.13). No comments that restate code. Async all the way for I/O. Aware datetimes only (UTC internally).
9. **Commit** at the end with the message given in the prompt, then tick the prompt in **Progress**.
10. **Final report** (short): files changed, number of tests, gate results, any deviation from the spec and why, anything the human must do next.

---

# Part 2 — Specification

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

---

# Part 3 — Prompts

## Prompt 0 — Pre-flight (you, not an agent)

- [ ] **0.1 Create the bot.** In Telegram, open **@BotFather** → `/newbot` → name `Theo dõi đơn hàng` → username ending in `bot` (e.g. `hozk_parcel_bot`) → copy the token. Then `/setjoingroups` → select the bot → **Disable** (private chats only).
- [ ] **0.2 Get your numeric Telegram ID.** Message **@userinfobot** → copy the `Id` number.
- [ ] **0.3 Check Telegram is reachable from this PC.**
  ```powershell
  Test-NetConnection api.telegram.org -Port 443 | Select-Object TcpTestSucceeded
  (Invoke-WebRequest https://api.telegram.org -UseBasicParsing -MaximumRedirection 0 -ErrorAction SilentlyContinue).StatusCode
  ```
  Expected: `True` and a status code (200/302). If it times out, your ISP is blocking Telegram: run a VPN client that exposes a local HTTP or SOCKS5 proxy and note its URL (e.g. `socks5h://127.0.0.1:1080`) for `TELEGRAM_PROXY_URL`.
- [ ] **0.4 Collect real tracking codes** (Shopee app → *Tôi* → *Đơn mua* → order → *Thông tin vận chuyển*). Ideally:
  - 1 SPX code **in transit** and 1 SPX code **delivered**
  - 1 J&T code **in transit** and 1 J&T code **delivered**, each with the **last 4 digits of the recipient's phone**
  - a returned/cancelled one of either carrier if you have it
- [ ] **0.5 Power settings.** *Settings → System → Power & sleep → Sleep: Never (when plugged in)*, or accept gaps while the PC sleeps.
- [ ] **0.6 Tools** (already verified on 2026-09-11): Python 3.13.5, git 2.50.1, `agy` 1.2.1.

Keep the token, your ID, the proxy URL, and the codes handy for Prompts 1–2. **Do not paste the token into an agent prompt**; you will type it into `.env` yourself.

---

## Prompt 1 — Scaffold, settings, logging

**Goal:** A clean, installable Python project with validated settings, safe logging, policy constants, and green quality gates.

**Spec:** §8.1, §9.1–9.3, §10, §11, §13.

**Preconditions:** Empty repo except `BUILD_PLAN.md` and `.git`.

**Create:**
- `pyproject.toml`, `.gitignore`, `.env.example`, `README.md` (short stub: what it is + "see BUILD_PLAN.md"), `requirements.lock.txt`
- `src/vn_parcel_bot/__init__.py` (`__version__ = "0.1.0"`)
- `src/vn_parcel_bot/config.py`, `constants.py`, `logging_setup.py`
- `tests/__init__.py` (empty), `tests/conftest.py`, `tests/test_config.py`, `tests/test_logging_setup.py`

**Build:**

1. `pyproject.toml` — exactly:
   ```toml
   [build-system]
   requires = ["hatchling>=1.25"]
   build-backend = "hatchling.build"

   [project]
   name = "vn-parcel-bot"
   version = "0.1.0"
   description = "Telegram bot that notifies about SPX Express and J&T Express Vietnam parcels"
   requires-python = ">=3.13"
   dependencies = [
     "python-telegram-bot[job-queue,socks]>=22.0",
     "httpx>=0.27",
     "aiosqlite>=0.20",
     "beautifulsoup4>=4.12",
     "python-dotenv>=1.0",
     "tzdata>=2024.1",
   ]

   [project.optional-dependencies]
   dev = ["pytest>=8.3", "pytest-asyncio>=0.24", "pytest-cov>=5.0", "respx>=0.21", "ruff>=0.6"]

   [project.scripts]
   vn-parcel-bot = "vn_parcel_bot.__main__:main"

   [tool.hatch.build.targets.wheel]
   packages = ["src/vn_parcel_bot"]

   [tool.pytest.ini_options]
   asyncio_mode = "auto"
   asyncio_default_fixture_loop_scope = "function"
   testpaths = ["tests"]
   addopts = "-ra"

   [tool.ruff]
   line-length = 100
   target-version = "py313"
   src = ["src", "tests", "scripts"]

   [tool.ruff.lint]
   select = ["E", "F", "W", "I", "B", "UP", "ASYNC", "S", "SIM", "RUF"]
   ignore = ["S101", "S311", "RUF001", "RUF002", "RUF003"]
   ```
2. `.gitignore`:
   ```
   .venv/
   __pycache__/
   *.py[cod]
   .pytest_cache/
   .ruff_cache/
   .coverage
   htmlcov/
   .env
   data/
   logs/
   tests/fixtures/_raw/
   probe_codes.local.txt
   *.sqlite3
   *.sqlite3-*
   ```
3. `.env.example` — every variable from §10.1 with its default and a one-line comment; `TELEGRAM_BOT_TOKEN=` and `ADMIN_TELEGRAM_ID=` empty; `TELEGRAM_PROXY_URL=` empty with comment `# e.g. socks5h://127.0.0.1:1080 if api.telegram.org is blocked`.
4. Environment:
   ```powershell
   py -3.13 -m venv .venv
   .\.venv\Scripts\python -m pip install --upgrade pip
   .\.venv\Scripts\python -m pip install -e ".[dev]"
   .\.venv\Scripts\python -m pip freeze --exclude-editable | Out-File -Encoding utf8 requirements.lock.txt
   ```
5. `constants.py` — exactly §9.2.
6. `config.py` — §9.1 + §10.1 validation. `from_env(env)` reads only from the given mapping (never `os.environ` directly), collects every problem into a list and raises `ConfigError("Invalid configuration:\n- …\n- …")`. Token regex `^\d+:[A-Za-z0-9_-]{30,}$`. `QUIET_HOURS`: key absent → `(22, 7)`; present but empty → `None`; else `H-H`. `TIMEZONE` validated by constructing `ZoneInfo`. Paths → `Path`. `LOG_LEVEL` upper-cased.
7. `logging_setup.py` — §9.3. `setup_logging` creates `log_dir`, clears existing root handlers (idempotent when called twice), attaches both handlers with the redact filter, sets `httpx`/`httpcore` to WARNING.
8. `tests/conftest.py` — fixture `valid_env() -> dict[str, str]` returning `{"TELEGRAM_BOT_TOKEN": "123456789:" + "A" * 35, "ADMIN_TELEGRAM_ID": "111"}` and fixture `settings(tmp_path, valid_env)` returning `Settings.from_env({**valid_env, "DB_PATH": str(tmp_path / "bot.sqlite3"), "LOG_DIR": str(tmp_path / "logs")})`.

**Tests (write first):**

`tests/test_config.py`
- `test_minimal_env_uses_defaults` — all defaults equal §9.1; `quiet_hours == (22, 7)`; `telegram_proxy_url is None`.
- `test_missing_required_reports_both` — `from_env({})` raises; message contains `TELEGRAM_BOT_TOKEN` and `ADMIN_TELEGRAM_ID`.
- `test_invalid_token_format` — `"abc"` rejected.
- `test_admin_id_must_be_positive_int` — `"x"`, `"0"`, `"-5"` rejected.
- `test_poll_interval_bounds` — `"4"` and `"241"` rejected; `"5"` and `"240"` accepted.
- `test_quiet_hours_variants` — `"22-7"` → `(22, 7)`; `""` → `None`; `"25-7"`, `"7-7"`, `"abc"` rejected.
- `test_invalid_timezone_rejected` — `"Mars/Base"`.
- `test_tz_property_loads_ho_chi_minh` — `settings.tz.key == "Asia/Ho_Chi_Minh"` (proves `tzdata` works on Windows).
- `test_proxy_scheme_validation` — `socks5h://127.0.0.1:1080` ok; `ftp://x` rejected; `""` → `None`.
- `test_log_level_normalized` — `"debug"` → `"DEBUG"`; `"LOUD"` rejected.
- `test_collects_multiple_errors` — two bad values → both mentioned in one exception.

`tests/test_logging_setup.py`
- `test_redact_filter_masks_secret_in_message_and_args` — record with msg `"url bot%s/getMe"` and args `(token,)` → formatted output contains `***`, not the token.
- `test_setup_logging_creates_log_file` — after logging one line, `log_dir/"bot.log"` exists and contains it.
- `test_httpx_loggers_quiet` — `logging.getLogger("httpx").level == logging.WARNING` and same for `httpcore`.
- `test_setup_logging_is_idempotent` — calling twice leaves exactly 2 root handlers (or 1 if stderr is None).
- `test_token_never_written` — log `f"token {settings.telegram_bot_token}"`; file content does not contain the token.

**Verify:**
```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m ruff format --check .
.\.venv\Scripts\python -c "import vn_parcel_bot, zoneinfo; print(vn_parcel_bot.__version__, zoneinfo.ZoneInfo('Asia/Ho_Chi_Minh'))"
git status --short
```
Expected: all tests pass; ruff clean; prints `0.1.0 Asia/Ho_Chi_Minh`; `git status` shows no `.venv`, `.env`, `data`, `logs`.

**Done when:** gates green; `requirements.lock.txt` lists `python-telegram-bot`, `httpx`, `aiosqlite`, `beautifulsoup4`, `tzdata`.

**Commit:** `chore: scaffold project with validated settings and safe logging`

**Then (you):** copy `.env.example` to `.env` and fill `TELEGRAM_BOT_TOKEN`, `ADMIN_TELEGRAM_ID`, and `TELEGRAM_PROXY_URL` if needed.

---

## Prompt 2 — HTTP client, live probe, real fixtures (GATE)

**Goal:** Prove with **real** tracking codes that both carriers return usable tracking data from this PC, capture sanitized fixtures, and document the exact request/response facts. Nothing after this prompt starts until this gate passes.

**Run interactively** — the agent may need you to open a browser's DevTools.

**Spec:** §5, §9.7 (`http.py` only), §11 (sanitization), §15 R1/R2/R4.

**Preconditions (you):**
- `.env` filled (Prompt 1 "Then").
- `probe_codes.local.txt` in the repo root (gitignored), one parcel per line, `#` comments allowed:
  ```
  # carrier code [last4]   state-you-believe
  spx SPXVN0xxxxxxxxxxx      in_transit
  spx SPXVN0yyyyyyyyyyy      delivered
  jt  84xxxxxxxxxx 1234      in_transit
  jt  84yyyyyyyyyy 5678      delivered
  ```

**Create:**
- `src/vn_parcel_bot/carriers/__init__.py` (empty for now)
- `src/vn_parcel_bot/carriers/http.py`
- `scripts/probe_carriers.py`
- `tests/test_http_client.py`
- `tests/fixtures/FIXTURES.md`
- `tests/fixtures/spx/in_transit.json`, `spx/delivered.json`, `spx/not_found.json` (+ `spx/returned.json` if available)
- `tests/fixtures/jt/in_transit.html`, `jt/delivered.html`, `jt/not_found.html` (+ `jt/returned.html` if available)

**Build:**

1. `carriers/http.py`:
   ```python
   DEFAULT_HEADERS = {
       "User-Agent": (
           "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
       ),
       "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
   }

   def make_http_client(settings: Settings) -> httpx.AsyncClient:
       return httpx.AsyncClient(
           timeout=settings.http_timeout_seconds,
           headers=DEFAULT_HEADERS,
           follow_redirects=True,
       )
   ```
2. `scripts/probe_carriers.py` (standalone CLI, `asyncio.run`):
   - `python scripts/probe_carriers.py carriers [--file probe_codes.local.txt]`
     - Parses the file; for each line sends the request using `make_http_client` (settings from `.env` via `python-dotenv` + `Settings.from_env(os.environ)`).
     - SPX: `GET https://spx.vn/api/v2/fleet_order/tracking/search?sls_tracking_number=<code>`.
     - J&T: `GET https://jtexpress.vn/tracking?type=track&billcode=<code>&cellphone=<last4>` (first attempt; see step 4).
     - Saves the raw body to `tests/fixtures/_raw/<carrier>_<code>_<YYYYmmdd-HHMMSS>.<json|html>`.
     - Prints one line per request: carrier, **masked** code (`first5…last3`), HTTP status, byte count; SPX: `retcode` and top-level keys of `data` (keys only); J&T: whether `Không tìm thấy dữ liệu` is present, whether `result-tracking` is present, and a count of elements that look like timeline items.
     - Sleeps 3–5 s between requests. Never prints response bodies.
   - `python scripts/probe_carriers.py telegram` — calls `getMe` through `httpx` (respecting `TELEGRAM_PROXY_URL`) and prints `OK @<bot_username>` or the exception class name. Never prints the token or URL.
3. Run `telegram`. If it fails, stop and tell the human to fix connectivity/proxy (Pre-flight 0.3) before continuing.
4. Run `carriers` and inspect the saved raw files (open them from disk; do not paste bodies containing personal data into the final report).
   - **SPX:** confirm real codes return a non-empty event list. If `data` is empty for real codes, try adding `Referer: https://spx.vn/track` and `Accept: application/json`; if still empty, ask the human to open `https://spx.vn/track` in Chrome, search a real code with DevTools → Network open, and share the tracking request's URL, method, and non-cookie headers (copy as cURL, with cookies removed). Repeat with those.
   - **J&T:** confirm real code + correct digits return tracking events. If not, download and read `https://jtexpress.vn/plugins/jtexpress/search/assets/js/tracking.js` and `tracking_cellphone.js`, find how the 4 digits are submitted (parameter name, GET vs POST, extra verify step, cookie/CSRF), update the probe, and retry. Also test one code **with wrong digits** and record what that page looks like.
   - Also probe one **fake** code per carrier (`SPXVN000000000000`, `840000000000` with `0000`) for the not-found fixtures.
5. Create sanitized fixtures from the raw captures:
   - Replace real tracking codes: SPX codes → `SPXVN000000000001`, `SPXVN000000000002`, …; J&T codes → `840000000001`, `840000000002`, …; keep the mapping consistent within each file.
   - Replace personal data (recipient/sender names, street addresses, full phone numbers, courier names and phones, order IDs) with obvious fakes (`Nguyễn Văn A`, `0900000000`, `123 Đường Mẫu`).
   - Keep structure, status codes, status texts, hub/city names, and timestamps unchanged.
   - HTML: you may delete `<script>`, `<style>`, header/footer, and unrelated sections, but keep the complete tracking-result container and the not-found marker exactly as served.
6. Write `tests/fixtures/FIXTURES.md` with, **per carrier**:
   - The exact working request (URL, method, params, required headers). Mark each header as required or not (tested by removing it).
   - Response structure: JSON paths (SPX) or CSS selectors (J&T) for the event list, event time, description, location, status code.
   - Timestamp format and timezone (e.g. Unix seconds UTC, or `dd/mm/yyyy HH:MM` local).
   - Event order as served (newest first or oldest first).
   - Not-found appearance (and wrong-digits appearance for J&T).
   - The exact texts/codes observed for **delivered** and **returned** (these become `DELIVERED_MARKERS` / `RETURNED_MARKERS`).
   - Observed tracking-code formats; if they contradict §5.3, say so.
   - Anti-bot behaviour observed (none / captcha / rate limit) and the number of requests made.
   - Date of capture.
7. Update the §5.1/§5.2 "Confidence" columns from Unverified → Verified (or document the real mechanism), in the same commit.

**Tests (write first):**

`tests/test_http_client.py`
- `test_client_defaults(settings)` — `async with make_http_client(settings) as c:` → `c.timeout.connect == settings.http_timeout_seconds`, `c.headers["User-Agent"] == DEFAULT_HEADERS["User-Agent"]`, `c.headers["Accept-Language"]` starts with `vi-VN`, `c.follow_redirects is True`.

**Verify:**
```powershell
.\.venv\Scripts\python scripts\probe_carriers.py telegram
.\.venv\Scripts\python scripts\probe_carriers.py carriers
.\.venv\Scripts\python -m pytest -q
git status --short
# No real code may appear in committed files:
Get-Content probe_codes.local.txt | Where-Object { $_ -and -not $_.StartsWith('#') } | ForEach-Object { ($_ -split '\s+')[1] } | ForEach-Object { Select-String -Path tests\fixtures\spx\*, tests\fixtures\jt\*, tests\fixtures\FIXTURES.md, BUILD_PLAN.md -Pattern $_ -SimpleMatch }
```
Expected: `OK @…`; each real code shows events; tests green; `git status` shows no `_raw/` or `probe_codes.local.txt`; the last command prints **nothing**.

**GATE — stop and report instead of committing if any of these is true:**
- Either carrier needs a captcha, a JavaScript challenge, a signed/rotating token, or a logged-in session to return real data.
- Real data could not be obtained for a carrier after the steps above.
- Telegram is unreachable even with the proxy.

Report what you saw and the options: (a) copy browser headers/cookies periodically, (b) headless browser (Playwright) for that carrier, (c) paid aggregator for that carrier, (d) drop that carrier from v1. The human decides; update Part 2 before any further prompt.

**Done when:** both carriers verified with real data; fixtures + `FIXTURES.md` committed and sanitized; §5.1/§5.2 confidence columns updated.

**Commit:** `test: capture sanitized SPX and J&T fixtures from live probes`

---

## Prompt 3 — Tracking codes and tracking models

**Goal:** Pure, fully tested building blocks: code normalization/detection and the carrier-neutral tracking data types, plus shared test fakes.

**Spec:** §5.3, §7 (event key), §9.5, §9.6, §13 (fakes).

**Preconditions:** Prompt 2 committed. Read `tests/fixtures/FIXTURES.md` — if it records code formats different from §5.3, Part 2 was already updated in Prompt 2; follow Part 2.

**Create:**
- `src/vn_parcel_bot/tracking_codes.py`
- `src/vn_parcel_bot/carriers/models.py`
- `tests/fakes.py`
- `tests/test_tracking_codes.py`, `tests/test_models.py`

**Build:**

1. `tracking_codes.py` — §9.5 with:
   ```python
   CarrierCode = Literal["spx", "jt"]
   _SPX_RE = re.compile(r"^SPXVN[0-9A-Z]{8,16}$")
   _JT_RE = re.compile(r"^\d{12}$")
   _SPX_FIND = re.compile(r"SPXVN[0-9A-Z]{8,16}")
   _JT_FIND = re.compile(r"(?<!\d)\d{12}(?!\d)")
   _STRIP_CHARS = ",;:()[]<>\"'"
   ```
   `extract_codes` collects `(match.start(), code)` from both patterns on `text.upper()`, sorts by position, de-duplicates preserving first occurrence.
2. `carriers/models.py` — §9.6:
   - `TrackingEvent.__post_init__`: `if self.time.tzinfo is None or self.time.utcoffset() is None: raise ValueError("TrackingEvent.time must be timezone-aware")`.
   - `TrackingEvent.key`:
     ```python
     def _norm(s: str) -> str:
         return " ".join(s.split()).casefold()

     @property
     def key(self) -> str:
         utc = self.time.astimezone(UTC).replace(microsecond=0).isoformat()
         raw = f"{utc}|{_norm(self.description)}|{_norm(self.location or '')}"
         return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
     ```
     (`hashlib.sha1(..., usedforsecurity=False)` to satisfy ruff `S324`.)
   - `TrackingResult.__post_init__`: `object.__setattr__(self, "events", tuple(sorted(self.events, key=lambda e: e.time)))` (Python's sort is stable).
   - `CarrierError`: stores attributes, `super().__init__(f"{carrier}:{reason}: {detail}")`.
   - `Carrier` is a `typing.Protocol` (not runtime-checkable).
3. `tests/fakes.py`:
   ```python
   class FakeClock:
       def __init__(self, start: datetime) -> None: ...     # must be aware
       def __call__(self) -> datetime: ...                  # current time
       def advance(self, delta: timedelta) -> None: ...
       def set(self, value: datetime) -> None: ...

   class FakeCarrier:
       def __init__(self, code: CarrierCode, *, needs_phone: bool = False,
                    display_name: str | None = None) -> None: ...
       results: dict[tuple[str, str | None], TrackingResult | CarrierError]
       calls: list[tuple[str, str | None]]
       async def fetch(self, http, tracking_number: str, phone_last4: str | None = None) -> TrackingResult: ...
       # unknown key -> TrackingResult(carrier=code, tracking_number=..., found=False)

   class FakeNotifier:
       def __init__(self, fail_with: Exception | None = None) -> None: ...
       sent: list[tuple[int, str, bool]]
       async def send(self, chat_id: int, text: str, *, silent: bool = False) -> None: ...  # records then raises fail_with if set

   def ev(minutes: int, description: str = "Đang vận chuyển", location: str | None = "Kho HCM",
          base: datetime = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)) -> TrackingEvent: ...
   ```

**Tests (write first):**

`tests/test_tracking_codes.py`
- `test_normalize_strips_spaces_dashes_dots_case` — `" spxvn 0533-8454.932c "` → `"SPXVN05338454932C"`.
- `test_normalize_strips_surrounding_punctuation` — `"(841000072647),"` → `"841000072647"`.
- `test_detect_spx_valid` — `"SPXVN05338454932C"` → `"spx"`; `"SPXVN" + "1"*8` → `"spx"`; `"SPXVN" + "1"*16` → `"spx"`.
- `test_detect_spx_invalid` — `"SPXVN"`, `"SPXVN" + "1"*7`, `"SPXVN" + "1"*17`, `"SPXTH05338454932"` → `None`.
- `test_detect_jt` — `"841000072647"` → `"jt"`; 11 and 13 digits → `None`.
- `test_detect_unknown` — `""`, `"ABC123"`, `"71426082060"` → `None`.
- `test_extract_codes_mixed_text_in_order` — `"Mã: spxvn05338454932c và J&T 841000072647."` → `["SPXVN05338454932C", "841000072647"]`.
- `test_extract_codes_dedupes` — same code twice → one item.
- `test_extract_codes_ignores_longer_digit_runs` — `"8410000726470"` → `[]`.
- `test_extract_codes_none` — `"xin chào"` → `[]`.
- `test_is_valid_last4` — `"1234"` True; `"123"`, `"12345"`, `"12a4"`, `" 1234"` False.

`tests/test_models.py`
- `test_event_requires_aware_time` — naive datetime → `ValueError`.
- `test_event_key_stable_and_16_hex` — same inputs → same key, `len == 16`, all hex.
- `test_event_key_ignores_whitespace_and_case` — `"Đang  giao hàng "` vs `"đang giao hàng"` → equal.
- `test_event_key_same_instant_different_tz` — `08:00+07:00` vs `01:00Z` → equal.
- `test_event_key_changes_with_description_or_location` — differ.
- `test_event_key_ignores_microseconds`.
- `test_result_sorts_events_ascending_stably` — input `[t2, t1a, t1b]` (t1a/t1b same time) → `(t1a, t1b, t2)`.
- `test_result_latest` — last event; empty → `None`.
- `test_carrier_error_str_and_attrs` — `str(CarrierError("spx", "network", "timeout")) == "spx:network: timeout"`.

**Verify:** quality gates (Standing rule 5).

**Done when:** gates green; no imports from `db`, `services`, or `bot` in these modules.

**Commit:** `feat: tracking code detection, tracking models, and test fakes`

---

## Prompt 4 — SPX carrier

**Goal:** `SpxCarrier.fetch` and `parse_spx_response` that turn the real SPX response into a `TrackingResult`, with all error paths mapped.

**Spec:** §5.1, §5.4, §9.7; `tests/fixtures/FIXTURES.md` (SPX section) is authoritative for field names, time format, and markers.

**Preconditions:** Prompt 3 committed.

**Create:** `src/vn_parcel_bot/carriers/spx.py`, `tests/test_spx.py`

**Build:**

1. Constants: `SPX_TRACKING_URL`, `DELIVERED_MARKERS`, `RETURNED_MARKERS` — markers are the **exact** status codes and/or texts recorded in FIXTURES.md. Compare texts with `casefold()` substring matching; compare codes with equality. If FIXTURES.md shows both a code and a text, prefer the code.
2. `parse_spx_response(payload, tracking_number)`:
   - `payload` not a dict, or missing `retcode` → `CarrierError("spx", "parse", "unexpected payload")`.
   - `retcode != 0` → `found=False` **only** if FIXTURES.md documents that retcode as not-found; otherwise `CarrierError("spx", "parse", f"retcode={retcode}")`.
   - Empty `data` or empty event list → `TrackingResult(carrier="spx", tracking_number=tracking_number, found=False)`.
   - Event list present but not a list, or an item lacks time/description → `CarrierError(..., "parse", ...)`.
   - Each item → `TrackingEvent(time=<aware datetime per FIXTURES.md>, description=<text stripped>, location=<text or None>, raw_status=<status code as str or None>)`. Unix timestamps → `datetime.fromtimestamp(ts, UTC)`; local strings → parse then `.replace(tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))`.
   - `delivered` = latest event matches `DELIVERED_MARKERS`; `returned` = any event matches `RETURNED_MARKERS` and not delivered.
3. `SpxCarrier.fetch(http, tracking_number, phone_last4=None)`:
   - `GET SPX_TRACKING_URL` with `params={"sls_tracking_number": tracking_number}` plus any **required** headers from FIXTURES.md.
   - `httpx.TimeoutException` / `httpx.TransportError` → `CarrierError("spx", "network", type(exc).__name__)`.
   - 403/429 → `blocked`; other non-200 → `http_status` with `detail=str(status)`.
   - `response.json()` failure → `parse` (`"invalid json"`); body that looks like an HTML challenge page → `blocked`.
   - Return `parse_spx_response(...)`.

**Tests (write first)** — load fixtures with a helper `load_json(name)` reading `tests/fixtures/spx/<name>.json` as UTF-8; replace `N`, `TEXT`, and `MARKER` below with the real values from the fixtures and FIXTURES.md:
- `test_parse_in_transit` — `found`, `len(events) == N`, ascending times, `latest.description == "TEXT"`, all times aware, `delivered is False`, `returned is False`.
- `test_parse_delivered` — `delivered is True`; latest event matches `MARKER`.
- `test_parse_returned` — only if `returned.json` exists (otherwise `pytest.skip("no returned fixture")`).
- `test_parse_not_found` — `found is False`, `events == ()`.
- `test_parse_times_match_fixture` — first event's local time (`astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))`) equals the value written in FIXTURES.md.
- `test_parse_rejects_non_dict` — `[]` → `CarrierError` reason `parse`.
- `test_parse_rejects_malformed_events` — fixture copy with the event list replaced by `"x"` → `parse`.
- `test_parse_unknown_retcode` — `{"retcode": 99999, "message": "x", "data": {}}` → `parse` (unless FIXTURES.md defines 99999).
- `test_fetch_sends_query_and_parses` (`respx.mock`) — route on `SPX_TRACKING_URL` asserting `request.url.params["sls_tracking_number"] == "SPXVN000000000001"`; returns in-transit fixture → `found`.
- `test_fetch_maps_http_errors` — parametrize `(403, "blocked"), (429, "blocked"), (500, "http_status"), (404, "http_status")`.
- `test_fetch_network_error` — `side_effect=httpx.ConnectTimeout("t")` → `network`.
- `test_fetch_invalid_json` — body `"<html>…</html>"` with 200 → `blocked` or `parse` exactly as implemented rule above (assert the rule).
- `test_carrier_attributes` — `code == "spx"`, `display_name == "SPX"`, `needs_phone is False`.

Use `async with httpx.AsyncClient() as http:` inside tests; `respx` intercepts it.

**Verify:** quality gates.

**Done when:** gates green; `pytest --cov=vn_parcel_bot.carriers.spx` ≥ 90 %.

**Commit:** `feat: SPX Express Vietnam carrier`

---

## Prompt 5 — J&T carrier and carrier registry

**Goal:** `JtCarrier.fetch` and `parse_jt_html` for J&T Express Vietnam HTML, plus the `CARRIERS` registry.

**Spec:** §5.2, §5.4, §9.7; `tests/fixtures/FIXTURES.md` (J&T section) is authoritative for the request mechanism, selectors, time format, and markers.

**Preconditions:** Prompt 4 committed.

**Create/modify:** create `src/vn_parcel_bot/carriers/jt.py`, `tests/test_jt.py`, `tests/test_carrier_registry.py`; modify `src/vn_parcel_bot/carriers/__init__.py`.

**Build:**

1. Constants: `JT_TRACKING_URL` (as proven in Prompt 2), `NOT_FOUND_MARKER = "Không tìm thấy dữ liệu"`, `DELIVERED_MARKERS`, `RETURNED_MARKERS` (exact texts from FIXTURES.md), and the CSS selectors as module constants (e.g. `RESULT_SELECTOR`, `EVENT_SELECTOR`, `TIME_SELECTOR`, `DESCRIPTION_SELECTOR`, `LOCATION_SELECTOR`) with values from FIXTURES.md.
2. `parse_jt_html(html, tracking_number)` using `BeautifulSoup(html, "html.parser")`:
   - Decide in this order:
     1. Events found with `EVENT_SELECTOR` inside the result container → **found**.
     2. Else `NOT_FOUND_MARKER` in page text, or an `.empty-vandon` element present → **not found**.
     3. Else → `CarrierError("jt", "parse", "no result or not-found marker")`.
   - An event missing time or description → `parse` error.
   - Times per FIXTURES.md (typically local `dd/mm/yyyy HH:MM[:SS]` → `ZoneInfo("Asia/Ho_Chi_Minh")`).
   - Text normalization: `" ".join(el.get_text(" ").split())`.
   - `delivered`/`returned` rules as in Prompt 4.
   - If the page can show several bills, only use the block for `tracking_number` (FIXTURES.md tells how blocks are identified).
3. `JtCarrier.fetch(http, tracking_number, phone_last4)`:
   - `phone_last4 is None` → `raise ValueError("J&T requires phone_last4")`.
   - Perform the request **exactly** as documented in FIXTURES.md (GET params or POST form, any preliminary request).
   - Same network/HTTP error mapping as SPX; a captcha/challenge page (per FIXTURES.md or containing `captcha`/`cf-challenge`) → `blocked`.
4. `carriers/__init__.py`:
   ```python
   CARRIERS: dict[CarrierCode, Carrier] = {"spx": SpxCarrier(), "jt": JtCarrier()}

   def get_carrier(code: CarrierCode) -> Carrier:
       return CARRIERS[code]
   ```

**Tests (write first)** — helper `load_html(name)` reads `tests/fixtures/jt/<name>.html` (UTF-8). Replace `N`/`TEXT` with fixture facts:

`tests/test_jt.py`
- `test_parse_in_transit` — `found`, `len(events) == N`, ascending, aware times, `latest.description == "TEXT"`, not delivered.
- `test_parse_delivered` — `delivered is True`.
- `test_parse_returned` — skip if no fixture.
- `test_parse_not_found_fixture` — `found is False`.
- `test_parse_not_found_marker_minimal` — `"<html><body><p>Không tìm thấy dữ liệu về vận đơn</p></body></html>"` → `found is False`.
- `test_parse_empty_vandon_minimal` — `'<div class="empty-vandon"></div>'` → `found is False`.
- `test_parse_unknown_page_raises` — `"<html><body>Bảo trì hệ thống</body></html>"` → `parse`.
- `test_parse_event_missing_time_raises` — in-transit fixture with the first time element removed (via BeautifulSoup in the test) → `parse`.
- `test_parse_time_matches_fixture` — first event local time equals FIXTURES.md value.
- `test_fetch_requires_phone` — `ValueError`.
- `test_fetch_sends_code_and_digits` (`respx`) — assert the request carries `840000000001` and `1234` in the documented place; returns in-transit fixture → `found`.
- `test_fetch_maps_http_errors` — `403/429 → blocked`, `500/404 → http_status`.
- `test_fetch_network_error` — `httpx.ReadTimeout` → `network`.
- `test_fetch_challenge_page_blocked` — 200 with `"<html>captcha</html>"` → `blocked`.
- `test_carrier_attributes` — `code == "jt"`, `display_name == "J&T"`, `needs_phone is True`.

`tests/test_carrier_registry.py`
- `test_registry_contains_both` — keys `{"spx", "jt"}`; `get_carrier("jt").needs_phone is True`.
- `test_registry_codes_match_keys` — each value's `.code` equals its key.

**Verify:** quality gates.

**Done when:** gates green; `pytest --cov=vn_parcel_bot.carriers` ≥ 90 %.

**Commit:** `feat: J&T Express Vietnam carrier and carrier registry`

---

## Prompt 6 — Database schema and repository

**Goal:** A migrated SQLite database and an async `Repository` that is the only code touching SQL.

**Spec:** §7 (SQL verbatim), §9.8.

**Preconditions:** Prompt 5 committed.

**Create:** `src/vn_parcel_bot/db/__init__.py` (empty), `db/schema.py`, `db/repo.py`, `tests/test_repo.py`

**Build:**

1. `schema.py`: `SCHEMA_VERSION = 1`; `MIGRATIONS = [<§7 SQL verbatim>]`;
   ```python
   async def migrate(conn: aiosqlite.Connection) -> None:
       (current,) = await (await conn.execute("PRAGMA user_version")).fetchone()
       for version in range(current, SCHEMA_VERSION):
           await conn.executescript(MIGRATIONS[version])
           await conn.execute(f"PRAGMA user_version = {version + 1}")
           await conn.commit()
   ```
   (`executescript` commits implicitly; that is fine for v1. Ruff `S608` does not apply because the version is an int we control — add `# noqa: S608` only if ruff flags it.)
2. `repo.py`:
   - `Repository.open(db_path)`: `Path(db_path).parent.mkdir(parents=True, exist_ok=True)`; `conn = await aiosqlite.connect(db_path)`; `conn.row_factory = aiosqlite.Row`; `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`, `PRAGMA busy_timeout=5000`; `await migrate(conn)`.
   - Private helpers: `_to_db(dt: datetime) -> str` (`dt.astimezone(UTC).isoformat(timespec="seconds")`; raise `ValueError` for naive) and `_from_db(s: str | None) -> datetime | None` (`datetime.fromisoformat`).
   - Row → `User` / `Parcel` mappers (`bool(row["is_admin"])`, etc.).
   - `upsert_user`: `INSERT … ON CONFLICT(telegram_id) DO UPDATE SET` only the fields that are not `None`; `created_at` set on insert only; new users default `is_allowed=0, is_admin=0`.
   - `add_parcel`: insert with `state='pending'`, `created_at=updated_at=now`; catch `sqlite3.IntegrityError` whose message contains `UNIQUE` → `DuplicateParcelError`; return `get_parcel(lastrowid)`.
   - `list_parcels(user_id, *, terminal_since)`: `WHERE user_id=? AND (state IN ('pending','in_transit') OR updated_at >= ?) ORDER BY created_at, id`.
   - `due_parcels(now)`: `JOIN users u ON u.telegram_id = p.user_id WHERE u.is_allowed = 1 AND p.state IN ('pending','in_transit') AND p.next_check_at <= ? ORDER BY p.next_check_at, p.id`.
   - `record_check_success`: `SET state=?, last_status_text=COALESCE(?, last_status_text), last_event_at=COALESCE(?, last_event_at), delivered_at=COALESCE(?, delivered_at), consecutive_failures=0, next_check_at=?, updated_at=?`.
   - `record_check_failure`: `UPDATE … SET consecutive_failures = consecutive_failures + 1, next_check_at=?, updated_at=? … RETURNING consecutive_failures` (SQLite ≥ 3.35 ships with Python 3.13).
   - `insert_events`: for each event in ascending order `INSERT OR IGNORE INTO events (...)`; if `cursor.rowcount == 1` the event is new; commit once; return new events in ascending order.
   - `list_events(parcel_id, limit)`: `SELECT … ORDER BY event_time DESC, id DESC LIMIT ?` then reverse to ascending; rebuild `TrackingEvent` (location/raw_status may be `None`).
   - `delete_terminal_before(cutoff)`: `DELETE FROM parcels WHERE state IN (<terminal>) AND updated_at < ?`; return `rowcount`.
   - Every write method commits.

**Tests (write first)** — fixture `repo` in the test module: `r = await Repository.open(tmp_path / "t.sqlite3")`, yield, `await r.close()`. Use `T0 = datetime(2026, 9, 1, 1, 0, tzinfo=UTC)` and `ev()` from `tests/fakes.py`.

- `test_migrate_sets_user_version_and_is_idempotent` — open, close, reopen → `PRAGMA user_version == 1`, no error.
- `test_foreign_keys_enabled` — `PRAGMA foreign_keys` returns 1.
- `test_upsert_user_insert_then_partial_update` — insert with `name="A"`; update with `is_allowed=True` only → name still `"A"`, allowed `True`, `created_at` unchanged.
- `test_set_default_phone_and_clear`.
- `test_default_phone_check_constraint` — raw `UPDATE users SET default_phone_last4='12a4'` raises `sqlite3.IntegrityError`.
- `test_add_parcel_and_get` — fields round-trip; `state == "pending"`; datetimes aware UTC.
- `test_add_parcel_duplicate_raises` — same user/carrier/code → `DuplicateParcelError`.
- `test_same_code_different_users_allowed`.
- `test_list_parcels_includes_recent_terminal_only` — active A, delivered B (updated 1 day ago), delivered C (updated 5 days ago), `terminal_since = now - 3 days` → `[A, B]` in created order.
- `test_count_active_parcels`.
- `test_due_parcels_filters_state_time_and_allowed` — due active of allowed user ✔; future `next_check_at` ✘; delivered ✘; due active of not-allowed user ✘; ordering by `next_check_at`.
- `test_insert_events_returns_only_new_ascending` — insert `[e2, e1]` → returns `[e1, e2]`; insert `[e1, e2, e3]` → `[e3]`; insert again → `[]`.
- `test_list_events_limit_returns_most_recent_ascending` — 5 events, `limit=3` → last three, ascending.
- `test_delete_parcel_cascades_events` — `count_events` is 0 afterwards.
- `test_record_check_success_resets_failures_and_keeps_nulls` — after two failures, success with `last_status_text=None` keeps previous text and sets failures 0.
- `test_record_check_failure_increments_and_returns` — returns 1 then 2; `next_check_at` stored.
- `test_set_label_and_clear`.
- `test_delete_terminal_before` — only terminal parcels older than cutoff removed; returns count.
- `test_meta_roundtrip_and_overwrite`.
- `test_naive_datetime_rejected` — `add_parcel(now=datetime(2026, 9, 1))` → `ValueError`.

**Verify:** quality gates.

**Done when:** gates green; `pytest --cov=vn_parcel_bot.db` ≥ 90 %.

**Commit:** `feat: SQLite schema and async repository`

---

## Prompt 7 — Texts and message formatting

**Goal:** Every user-visible string in one module and pure formatting functions that build HTML-safe messages.

**Spec:** §4, §6.5, §9.9, §17 (copy verbatim).

**Preconditions:** Prompt 6 committed.

**Create:** `src/vn_parcel_bot/texts.py`, `src/vn_parcel_bot/services/__init__.py` (empty), `services/formatting.py`, `tests/test_texts.py`, `tests/test_formatting.py`

> `format_add_outcome` needs `AddOutcome` from Prompt 8. To keep this prompt self-contained, **create `services/parcels.py` now containing only** `AddKind` and the `AddOutcome` dataclass exactly as §9.10. Prompt 8 adds `ParcelService` to the same file.

**Build:**

1. `texts.py` — §17 verbatim (UTF-8 file).
2. `formatting.py` rules:
   - Escape every dynamic value with `html.escape(value, quote=False)`: labels, codes, descriptions, locations, names, error details, refs.
   - `parcel_title(p)` → escaped label if set, else escaped tracking number.
   - `carrier_name(code)` → `CARRIER_NAMES[code]`.
   - `format_time(dt, tz)` → `dt.astimezone(tz).strftime(TIME_FORMAT)`.
   - `format_event_update`: `UPDATE_HEADER`, then — if `len(new_events) > MAX_EVENTS_IN_UPDATE` — `UPDATE_MORE.format(count=len(new_events) - MAX_EVENTS_IN_UPDATE)`, then one `UPDATE_LINE` (+ `UPDATE_LOCATION` if location) per event for the last `MAX_EVENTS_IN_UPDATE` events in chronological order; then a blank line and `UPDATE_DELIVERED` if `delivered`, else `UPDATE_RETURNED` if `returned`. Result passes through `truncate_message`.
   - `format_parcel_list`: empty → `LIST_EMPTY`; else `LIST_HEADER` + blank line + items joined by `"\n"`. `status` = escaped `last_status_text` or `STATE_TEXT[state]`; `time_suffix` = `LIST_TIME_SUFFIX.format(time=…)` when `last_event_at` else `""`; index starts at 1.
   - `format_history`: `HISTORY_HEADER` then events **newest first** (at most `MAX_EVENTS_IN_HISTORY`) as `UPDATE_LINE`(+location), or `HISTORY_EMPTY`.
   - `format_add_outcome(outcome, tz, *, max_parcels)`:
     - `added` + `result.found` + `parcel.state == "delivered"` → `ADDED_DELIVERED` (time = latest event).
     - `added` + `result.found` → `ADDED_FOUND` (status = escaped latest description, time = latest event).
     - `added` + `error` → `ADDED_ERROR`.
     - `added` + not found → `ADDED_PENDING` (+ `ADDED_PENDING_JT_HINT` when carrier is `jt`).
     - `needs_phone` → `ASK_PHONE`; `duplicate` → `DUPLICATE`; `limit` → `LIMIT_REACHED`; `invalid_code` → `UNKNOWN_CODE`; `invalid_phone` → `INVALID_PHONE`.
   - `format_needs_phone_multi(codes)` → codes as `<code>…</code>` lines.
   - `format_expired(p)` → `EXPIRED`; `format_stale(p)` → `STALE`.
   - `format_carrier_alert(carrier, count, detail)` → `ALERT_CARRIER` with detail escaped and cut to 200 chars.
   - `format_users(users, active_counts, admin_id)` → `USERS_HEADER` + one `USERS_ITEM` per user; role: admin id → `ROLE_ADMIN`, allowed → `ROLE_MEMBER`, else `ROLE_BLOCKED`; name escaped or `"—"`.
   - `format_health(last_poll_at, report, active, users, tz)` → `HEALTH`; `last_poll` = `format_time` or `HEALTH_NEVER`; `fetches`/`new_events` from report or `0`; `failures` = `"spx=2, jt=0"` style or `"0"`.
   - `truncate_message(text, limit)` → unchanged if `len <= limit`; else cut to the last `"\n"` before `limit - 1` (or hard cut if none) and append `"…"`; result length ≤ limit.

**Tests (write first)** — build `Parcel` objects directly with a helper `make_parcel(**overrides)` in the test file; `TZ = ZoneInfo("Asia/Ho_Chi_Minh")`.

`tests/test_texts.py`
- `test_all_texts_are_html_safe` — for every `str` constant in `texts`, after removing allowed tags (`<b>`, `</b>`, `<code>`, `</code>`) there is no raw `<`, `>`, and every `&` starts an entity (`&amp;`, `&lt;`, `&gt;`).
- `test_placeholders_format_without_error` — each template formats with dummy kwargs for its placeholders (parse with `string.Formatter().parse`).
- `test_state_maps_cover_all_states` — `STATE_EMOJI` and `STATE_TEXT` keys equal the six states.

`tests/test_formatting.py`
- `test_title_prefers_escaped_label` — label `"<Áo & quần>"` → `"&lt;Áo &amp; quần&gt;"`; no label → tracking number.
- `test_format_time_local` — `01:30Z` → `"01/09 08:30"`.
- `test_event_update_lines_and_location` — 2 events, one without location → header, two lines, `" (Kho HCM)"` only on the first.
- `test_event_update_escapes_description` — description `"<script>"` appears as `&lt;script&gt;`.
- `test_event_update_more_than_ten` — 13 events → contains `"… và 3 cập nhật trước đó"` and exactly 10 bullet lines, the last being the newest.
- `test_event_update_delivered_footer` — `delivered=True` → ends with `UPDATE_DELIVERED`; `returned=True` → `UPDATE_RETURNED`; both False → neither.
- `test_parcel_list_empty` / `test_parcel_list_items` — numbering, emoji per state, `STATE_TEXT` fallback, time suffix only with `last_event_at`.
- `test_history_newest_first_and_empty`.
- `test_add_outcome_each_kind` — parametrized over all kinds and the four `added` variants, asserting the distinguishing phrase of each template (and the J&T hint only for `jt`).
- `test_users_roles` — admin, member, blocked.
- `test_health_never_and_with_report`.
- `test_truncate_message` — short unchanged; long multi-line cut at a line break, ends with `…`, `len ≤ limit`; single long line hard-cut.

**Verify:** quality gates.

**Done when:** gates green; `formatting.py` has no I/O imports (`httpx`, `aiosqlite`, `telegram`).

**Commit:** `feat: Vietnamese text catalog and message formatting`

---

## Prompt 8 — Parcel service

**Goal:** All user-facing parcel rules (add, list, resolve, remove, rename, history, default phone) in `ParcelService`, tested against a real temp database and fake carriers.

**Spec:** §4.1, §4.3, §9.10, §6.4 (backoff formula for a failed first fetch).

**Preconditions:** Prompt 7 committed (`services/parcels.py` already holds `AddKind`/`AddOutcome`).

**Modify:** `src/vn_parcel_bot/services/parcels.py` (add `ParcelService`). **Create:** `tests/test_parcels_service.py`.

**Build:**

1. `ParcelService.__init__` stores dependencies; carriers is a `Mapping[CarrierCode, Carrier]`.
2. `add(user, raw_code, phone_last4=None)` — exactly §4.3:
   ```
   code = normalize_code(raw_code); carrier_code = detect_carrier(code)
   if carrier_code is None: return AddOutcome("invalid_code")
   carrier = carriers[carrier_code]
   last4 = None
   if carrier.needs_phone:
       if phone_last4 is not None:
           if not is_valid_last4(phone_last4): return AddOutcome("invalid_phone", code=code)
           last4 = phone_last4
       else:
           last4 = user.default_phone_last4
       if last4 is None: return AddOutcome("needs_phone", code=code)
   if await repo.find_parcel(user.telegram_id, code): return AddOutcome("duplicate", code=code)
   if await repo.count_active_parcels(user.telegram_id) >= settings.max_parcels_per_user:
       return AddOutcome("limit", code=code)
   now = self._now()
   parcel = await repo.add_parcel(user_id=…, carrier=carrier_code, tracking_number=code,
                                  phone_last4=last4, now=now, next_check_at=now + settings.poll_interval)
   try:
       result = await carrier.fetch(http, code, last4)
   except CarrierError as err:
       n = parcel.consecutive_failures + 1
       await repo.record_check_failure(parcel.id, next_check_at=now + min(settings.poll_interval * 2**n, MAX_BACKOFF), now=now)
       return AddOutcome("added", code=code, parcel=await repo.get_parcel(parcel.id), error=err)
   if result.found:
       await repo.insert_events(parcel.id, result.events, now)
       state = "delivered" if result.delivered else "returned" if result.returned else "in_transit"
       latest = result.latest
       await repo.record_check_success(parcel.id, state=state,
           last_status_text=latest.description if latest else None,
           last_event_at=latest.time if latest else None,
           next_check_at=now + settings.poll_interval, now=now,
           delivered_at=latest.time if state == "delivered" and latest else None)
   else:
       await repo.record_check_success(parcel.id, state="pending", last_status_text=None,
           last_event_at=None, next_check_at=now + settings.poll_interval, now=now)
   return AddOutcome("added", code=code, parcel=await repo.get_parcel(parcel.id), result=result)
   ```
   Also catch `DuplicateParcelError` from `add_parcel` (race) → `duplicate`. SPX ignores any `phone_last4` passed (stored as `None`).
3. `list_for(user_id)` → `repo.list_parcels(user_id, terminal_since=now - DELIVERED_VISIBLE_FOR)`.
4. `resolve(user_id, ref)`: `ref = ref.strip()`; if `ref` matches `^\d{1,3}$` → 1-based index into `list_for` (out of range → `None`); else `repo.find_parcel(user_id, normalize_code(ref))`.
5. `remove` → resolve, `delete_parcel`, return the parcel (or `None`).
6. `rename(user_id, ref, label)` → resolve; label `None`/blank → clear; else `label.strip()[:MAX_LABEL_LENGTH]`; return refreshed parcel.
7. `history(user_id, ref)` → resolve; `repo.list_events(parcel.id, MAX_EVENTS_IN_HISTORY)`.
8. `set_default_phone(user_id, last4)` → `None` clears; invalid → `ValueError`.
9. Log INFO `"parcel added user=%s carrier=%s code=%s state=%s"` with the masked code (`code[:5] + "…" + code[-3:]`). Put the masking helper `mask_code(code: str) -> str` in `tracking_codes.py` and add a test for it in `tests/test_tracking_codes.py`.

**Tests (write first)** — fixtures: `repo` (temp DB), `clock = FakeClock(T0)`, `spx = FakeCarrier("spx")`, `jt = FakeCarrier("jt", needs_phone=True)`, `service = ParcelService(repo, {"spx": spx, "jt": jt}, http=None, settings=settings, now=clock)` (fakes ignore `http`), `user = await repo.upsert_user(1, now=T0, name="A", is_allowed=True)`.

Codes used: `SPX = "SPXVN000000000001"`, `JT = "840000000001"`.

- `test_add_invalid_code` — `"hello"` → `invalid_code`; no fetch.
- `test_add_spx_found_in_transit` — result with 2 events → `added`, parcel `in_transit`, `last_status_text` = latest description, `count_events == 2`, `spx.calls == [(SPX, None)]`.
- `test_add_normalizes_code` — `" spxvn 0000-0000-0000 1"` → stored `SPX`.
- `test_add_spx_delivered_sets_delivered_at` — `delivered=True` → state `delivered`, `delivered_at == latest.time`.
- `test_add_spx_not_found_stays_pending` — `pending`, `consecutive_failures == 0`, `result.found is False`.
- `test_add_carrier_error_records_backoff` — error → `added`, `error` set, failures 1, `next_check_at == T0 + 40 min` (interval 20 × 2¹).
- `test_add_jt_without_phone_needs_phone` — `needs_phone`, nothing stored, no fetch.
- `test_add_jt_uses_default_phone` — user default `"1111"` → `jt.calls == [(JT, "1111")]`, parcel `phone_last4 == "1111"`.
- `test_add_jt_override_wins` — default `"1111"`, override `"2222"` → uses `"2222"`.
- `test_add_jt_invalid_override` — `"12a4"` → `invalid_phone`.
- `test_add_duplicate` — second add → `duplicate`, fetch called once in total.
- `test_add_limit` — settings with `MAX_PARCELS_PER_USER="2"` → third active add → `limit`.
- `test_list_for_hides_old_terminal` — delivered parcel updated 4 days ago hidden; updated 1 day ago shown.
- `test_resolve_by_index_and_code` — `"1"`, `"2"`, code, lowercase code; `"0"`, `"9"` → `None`.
- `test_remove_returns_parcel_and_deletes` / `test_remove_unknown_returns_none`.
- `test_rename_sets_truncates_and_clears` — 60-char label → 40 chars; `None` clears.
- `test_history_returns_recent_events_ascending` — (the formatter reverses for display).
- `test_set_default_phone_valid_invalid_clear`.
- `test_other_users_parcels_invisible` — user 2 cannot resolve/remove user 1's parcel.

**Verify:** quality gates.

**Done when:** gates green; `pytest --cov=vn_parcel_bot.services.parcels` ≥ 90 %.

**Commit:** `feat: parcel service with add, list, remove, label, history`

---

## Prompt 9 — Poller

**Goal:** The polling engine: due selection, request de-duplication, polite pacing, diffing, notifications, state transitions, backoff, alerts, quiet hours, housekeeping.

**Spec:** §5.5, §6 (entire), §9.2, §9.11.

**Preconditions:** Prompt 8 committed.

**Create:** `src/vn_parcel_bot/services/poller.py`, `tests/test_poller.py`

**Build:**

1. `Notifier` protocol and `PollReport` exactly as §9.11. `to_json()` → `json.dumps` of all fields with datetimes as ISO strings, `ensure_ascii=False`.
2. `Poller.__init__` stores deps; `self._lock = asyncio.Lock()`.
3. `run_cycle(*, only_user_id=None, wait=False)`:
   - If `self._lock.locked()` and not `wait` → return `PollReport(started_at=now, finished_at=now, skipped=True)`.
   - `async with self._lock:` run the algorithm in §6.2.
   - Parcels: `repo.active_parcels_for_user(only_user_id)` when given, else `repo.due_parcels(now)`.
   - Group key `(carrier, tracking_number, phone_last4)`; keep group order by first parcel's position.
   - Per carrier: `asyncio.gather(*(self._run_carrier(code, groups) for code, groups in by_carrier.items()))`.
   - `_run_carrier`: for index `i`, `if i > 0: await self._sleep(settings.request_delay_seconds + self._rand() * JITTER_SECONDS)`; `report.fetches += 1`; fetch; on `CarrierError` → `_handle_failure` for each parcel; else `_handle_result` for each parcel.
   - `report.parcels_checked = len(parcels)`.
4. `_handle_result(parcel, result, now)` — §6.3 steps 1–2. Delivered/returned footer only when `parcel.state` was not already that state. Send via `_notify(parcel.user_id, text)`. Increase `report.new_events` by `len(new)`.
5. Stale check (§6.3 step 3) — for parcels processed in this cycle whose refreshed state is `in_transit` and `last_event_at` older than `STALE_AFTER` → `set_state("stale")`, send `format_stale`.
6. `_handle_failure(parcel, err, now)`:
   - `n_prev = parcel.consecutive_failures`; `delay = min(settings.poll_interval * 2 ** (n_prev + 1), MAX_BACKOFF)`; `n = await repo.record_check_failure(parcel.id, next_check_at=now + delay, now=now)`.
   - `report.failures[carrier] = report.failures.get(carrier, 0) + 1`.
   - If `n == FAILURE_ALERT_THRESHOLD` → mark carrier for alert with `(n, str(err))`.
   - Log WARNING with masked code and `err.reason`.
   - Not-found-but-had-events is routed here with `CarrierError(carrier, "parse", "events disappeared")`.
7. Carrier alerts after all carriers finish: alert if marked, or if `fetches_for_carrier >= CARRIER_ALL_FAILED_MIN_FETCHES` and all of them failed. Cooldown: read `meta["alert:<carrier>"]`; skip if `now - last < ALERT_COOLDOWN`; else send `format_carrier_alert` to `settings.admin_telegram_id` (never silent) and store `now`.
8. `_notify(chat_id, text)`: `silent = self.is_quiet(now)`; `await notifier.send(chat_id, truncate_message(text), silent=silent)`; on any exception log WARNING and continue; count `report.messages_sent` only on success.
9. `is_quiet(at)`: `quiet_hours is None` → False; `(start, end)`; `h = at.astimezone(settings.tz).hour`; `start < end` → `start <= h < end`; else `h >= start or h < end`.
10. Housekeeping: `repo.delete_terminal_before(now - PURGE_AFTER)`; set `meta["last_poll_report"]` and `meta["last_poll_at"]`; log INFO one summary line with counts.
11. `only_user_id` cycles do **not** update `last_poll_at` (it reflects scheduled cycles) but do run everything else.

**Tests (write first)** — fixtures: temp `repo`, `clock = FakeClock(T0)` with `T0 = datetime(2026, 9, 1, 5, 0, tzinfo=UTC)` (12:00 local, not quiet), `spx`, `jt`, `notifier = FakeNotifier()`, `sleeps: list[float]` with `async def fake_sleep(s): sleeps.append(s)`, `rand=lambda: 0.5`, `poller = Poller(repo, {"spx": spx, "jt": jt}, None, notifier, settings, clock, fake_sleep, rand)`. Helper `add(user_id, code, carrier, last4=None, due=True)` inserts a parcel directly via `repo.add_parcel` with `next_check_at = T0` (due) or `T0 + 1h`. Users 1 (admin id from settings, allowed) and 2 (allowed).

- `test_no_due_parcels` — report zeros, no calls, no messages.
- `test_skips_not_yet_due` — `due=False` → no fetch.
- `test_new_events_notify_once` — result with 2 events → one message to user 1 containing both descriptions; state `in_transit`; second cycle (advance 20 min) with same result → no new message.
- `test_only_new_events_in_second_message` — cycle 1 events `[e1]`; cycle 2 `[e1, e2]` → second message contains e2's description and not e1's.
- `test_same_code_two_users_one_fetch_two_messages` — `spx.calls` length 1; `notifier.sent` to 1 and 2.
- `test_jt_groups_by_phone` — same J&T code with digits `1111` and `2222` → two fetches.
- `test_pacing_sleeps_between_same_carrier_only` — three SPX parcels + one J&T → `sleeps == [4.0, 4.0]` (3.0 + 0.5 × 2.0).
- `test_delivered_transition` — delivered result → state `delivered`, message ends with delivered footer; next cycle (advance 1 day) → no fetch.
- `test_delivered_footer_not_repeated` — parcel already `delivered` is never polled (assert via `due_parcels`), and a parcel `in_transit` → delivered gets the footer exactly once.
- `test_not_found_young_stays_pending_no_message`.
- `test_not_found_after_seven_days_expires` — parcel `created_at = T0 - 8 days` → state `expired`, one `EXPIRED` message.
- `test_not_found_with_existing_events_counts_failure` — pre-insert an event → failures 1, state unchanged, no user message.
- `test_failure_backoff_schedule` — consecutive errors: `next_check_at` = `T0+40m`, then (clock at that time) `+80m`, `+160m`, `+320m`, then capped at `+6h`.
- `test_alert_on_fifth_failure_with_cooldown` — drive one parcel to 5 failures → exactly one message to admin containing `ALERT_CARRIER` phrase; a 6th failure within 6 h → no second alert; after 6 h and a new threshold crossing on another parcel → alert again.
- `test_alert_when_all_fetches_fail_min_three` — three distinct SPX parcels all failing in one cycle → one alert; two failing → none.
- `test_stale_after_thirty_days` — `in_transit` parcel with `last_event_at = T0 - 31 days`, result has no new events → state `stale`, `STALE` message.
- `test_quiet_hours_silent_flag` — clock at 16:00Z (23:00 local) → `sent[0][2] is True`; at 05:00Z → False; `QUIET_HOURS=""` → always False.
- `test_is_quiet_wraparound_and_normal_ranges` — parametrized hours for `(22, 7)` and `(1, 5)`.
- `test_revoked_user_not_polled` — user 2 `is_allowed=False` → their parcel not fetched.
- `test_only_user_id_ignores_schedule` — `due=False` parcel of user 2 fetched when `only_user_id=2`; user 1 parcel not fetched; `last_poll_at` meta unchanged.
- `test_skipped_when_locked` — acquire `poller._lock` manually → `run_cycle()` returns `skipped=True` immediately; with `wait=True` inside a task it completes after release.
- `test_notifier_failure_does_not_stop_cycle` — `FakeNotifier(fail_with=RuntimeError())` → events still stored, second parcel still processed, `messages_sent == 0`.
- `test_purges_old_terminal` — delivered parcel updated 31 days ago is deleted.
- `test_report_saved_to_meta` — `json.loads(meta["last_poll_report"])` has keys `fetches`, `new_events`, `failures`, `skipped`.

**Verify:** quality gates.

**Done when:** gates green; `pytest --cov=vn_parcel_bot.services.poller` ≥ 90 %.

**Commit:** `feat: poller with diffing, backoff, alerts, and quiet hours`

---

## Prompt 10 — Telegram bot layer and entry point

**Goal:** Wire everything into a runnable bot: authorization gate, user and admin commands, the J&T phone flow, notifier, job scheduling, error handling, single-instance lock, and `python -m vn_parcel_bot`.

**Spec:** §3, §4, §6.1, §9.4, §9.12, §11, §12.

**Preconditions:** Prompt 9 committed.

**Create:**
- `src/vn_parcel_bot/single_instance.py`
- `src/vn_parcel_bot/bot/__init__.py` (empty), `bot/deps.py`, `bot/parsing.py`, `bot/auth.py`, `bot/commands.py`, `bot/notifier.py`, `bot/handlers_user.py`, `bot/handlers_admin.py`, `bot/app.py`

> Import direction (no cycles): `deps` ← `auth`, `handlers_user`, `handlers_admin` ← `app` ← `__main__`. `deps.py` holds `Deps` and `get_deps` (§9.12); nothing in `bot/` imports `app.py` except `__main__.py`.
- `src/vn_parcel_bot/__main__.py`
- `tests/test_single_instance.py`, `tests/test_bot_parsing.py`, `tests/test_auth.py`, `tests/test_notifier.py`, `tests/test_app.py`, `tests/test_main.py`

**Build:**

1. `single_instance.py`:
   ```python
   class SingleInstanceLock:
       def __init__(self, path: Path) -> None:
           self._path = path
           self._fh = None

       def __enter__(self):
           self._path.parent.mkdir(parents=True, exist_ok=True)
           fh = open(self._path, "a+b")  # noqa: SIM115
           try:
               fh.seek(0)
               if sys.platform == "win32":
                   import msvcrt
                   msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
               else:
                   import fcntl
                   fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
           except OSError as exc:
               fh.close()
               raise SingleInstanceError(f"lock held: {self._path}") from exc
           self._fh = fh
           return self
       # __exit__: unlock (msvcrt.LK_UNLCK after seek(0) / fcntl.LOCK_UN), close, ignore OSError on unlock
   ```
2. `bot/parsing.py` — §9.12:
   - `parse_track_args(args)`: empty → `None`. If `len(args) >= 2` and `is_valid_last4(args[-1])` and `detect_carrier(normalize_code("".join(args[:-1])))` is not `None` → `(normalize_code("".join(args[:-1])), args[-1])`. Otherwise `(normalize_code("".join(args)), None)`. (So `/track SPXVN 0000 0000 0001` keeps `0001` as part of the code.)
   - `parse_ref_and_text(args)`: empty → `None`; else `(args[0], " ".join(args[1:]).strip() or None)`.
   - `route_text(text, has_pending)`: §4.2 → `TextRoute` kinds `phone_for_pending`, `codes`, `invalid_phone`, `unknown`.
3. `bot/auth.py`:
   - `is_authorized(user, telegram_id, admin_id)` → `telegram_id == admin_id or (user is not None and user.is_allowed)`.
   - `gate(update, context)` (registered as `TypeHandler(Update, gate)` in group `-1`):
     - No `effective_user` or chat type not `private` → `raise ApplicationHandlerStop`.
     - `deps = get_deps(context)`; `db_user = await deps.repo.get_user(uid)`.
     - Not authorized → if `update.effective_message`: reply `NOT_ALLOWED.format(user_id=uid)`; `raise ApplicationHandlerStop`.
     - Authorized → `await deps.repo.upsert_user(uid, now=…, name=update.effective_user.full_name)`.
   - `admin_only(handler)` — `functools.wraps`; if `update.effective_user.id != context.bot_data["settings"].admin_telegram_id` → reply `ADMIN_ONLY` and return.
4. `bot/commands.py` — `BOT_COMMANDS` exactly §9.12.
5. `bot/notifier.py`:
   ```python
   class TelegramNotifier:
       def __init__(self, bot: Bot) -> None: self._bot = bot
       async def send(self, chat_id: int, text: str, *, silent: bool = False) -> None:
           try:
               await self._bot.send_message(
                   chat_id=chat_id, text=text, parse_mode=ParseMode.HTML,
                   disable_notification=silent,
                   link_preview_options=LinkPreviewOptions(is_disabled=True),
               )
           except Forbidden:
               log.info("user %s blocked the bot", chat_id)
   ```
6. Reply helper (in `handlers_user.py`, imported by admin handlers):
   ```python
   async def reply(update: Update, text: str) -> None:
       await update.effective_message.reply_text(
           truncate_message(text), parse_mode=ParseMode.HTML,
           link_preview_options=LinkPreviewOptions(is_disabled=True))
   ```
7. `bot/handlers_user.py` — one async function per command; each gets `deps = get_deps(context)`, `user = await deps.repo.get_user(update.effective_user.id)`, `tz = deps.settings.tz`:
   - `start`: `WELCOME.format(name=escape(first_name))` + `"\n\n"` + `HELP`.
   - `help_cmd`: `HELP`.
   - `track_cmd`: `parse_track_args(context.args)`; `None` → `USAGE_TRACK`; else `_add_and_reply(update, context, user, code, last4)`.
   - `_add_and_reply`: `outcome = await deps.parcels.add(user, code, last4)`; if `needs_phone` → `context.user_data["pending_jt"] = outcome.code`; else `context.user_data.pop("pending_jt", None)`; reply `format_add_outcome(outcome, tz, max_parcels=settings.max_parcels_per_user)`.
   - `text_message` (`MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE)`):
     - `route = route_text(update.effective_message.text, "pending_jt" in context.user_data)`.
     - `phone_for_pending` → `code = context.user_data.pop("pending_jt")`; `_add_and_reply(..., code, route.last4)`.
     - `codes` with one code → `context.user_data.pop("pending_jt", None)`; `_add_and_reply(..., code, None)`.
     - `codes` with several → pop pending; for each code: `outcome = await deps.parcels.add(user, code)`; collect `needs_phone` codes; reply each other outcome; finally, if collected → `format_needs_phone_multi(collected)`.
     - `invalid_phone` → `INVALID_PHONE`; `unknown` → `UNKNOWN_CODE`.
   - `list_cmd`: `format_parcel_list(await deps.parcels.list_for(uid), tz)`.
   - `status_cmd`: no args → `USAGE_REF.format(command="status")`; `history(uid, " ".join(context.args))`; `None` → `PARCEL_NOT_FOUND`; else `format_history`.
   - `label_cmd`: `parse_ref_and_text`; `None` → `USAGE_LABEL`; `rename`; `None` → `PARCEL_NOT_FOUND`; label set → `LABEL_SET`, cleared → `LABEL_CLEARED`.
   - `remove_cmd`: usage / not found / `REMOVED`.
   - `phone_cmd`: no args → `PHONE_SHOW` or `PHONE_NONE`; `clear` (case-insensitive) → clear + `PHONE_CLEARED`; valid 4 digits → set + `PHONE_SET`; else `INVALID_PHONE`.
   - `check_cmd`: cooldowns in `context.bot_data.setdefault("check_cooldowns", {})`; if `now - last < CHECK_COOLDOWN` → `CHECK_TOO_SOON` with remaining minutes rounded up; else store now, reply `CHECK_STARTED`, `report = await deps.poller.run_cycle(only_user_id=uid, wait=True)`, reply `CHECK_DONE`.
   - `cancel_cmd`: pop pending → `CANCELLED` / `NOTHING_TO_CANCEL`.
   - `unknown_command` (`MessageHandler(filters.COMMAND & filters.ChatType.PRIVATE)`, registered **last**): `UNKNOWN_COMMAND`.
8. `bot/handlers_admin.py` (all wrapped with `@admin_only`):
   - `allow_cmd`: first arg must be a positive int else `USAGE_ALLOW`; name = rest or `None`; `upsert_user(id, now=…, name=name, is_allowed=True)`; reply `ALLOWED` (`name_suffix = f" ({escape(name)})"` or `""`); then `try: await context.bot.send_message(id, ALLOWED_NOTICE, parse_mode=HTML) except TelegramError: pass`.
   - `revoke_cmd`: int check; admin id → `CANNOT_REVOKE_ADMIN`; else `upsert_user(id, now=…, is_allowed=False)` → `REVOKED`.
   - `users_cmd`: `format_users(users, {u.telegram_id: await repo.count_active_parcels(u.telegram_id) …}, admin_id)`.
   - `health_cmd`: meta `last_poll_at`/`last_poll_report` → `format_health(…, active=await repo.count_all_active(), users=len(await repo.list_users()), tz)`.
9. `bot/deps.py`: the `Deps` dataclass and `get_deps(context)` → `context.bot_data["deps"]`, exactly §9.12.
10. `bot/app.py`:
   - `build_application(settings)`:
     ```python
     builder = (Application.builder().token(settings.telegram_bot_token)
                .post_init(_post_init).post_shutdown(_post_shutdown))
     if settings.telegram_proxy_url:
         builder = (builder.request(HTTPXRequest(proxy=settings.telegram_proxy_url))
                    .get_updates_request(HTTPXRequest(proxy=settings.telegram_proxy_url)))
     app = builder.build()
     app.bot_data["settings"] = settings
     app.add_handler(TypeHandler(Update, gate), group=-1)
     private = filters.ChatType.PRIVATE
     for name, fn in [("start", start), ("help", help_cmd), ("track", track_cmd), ("list", list_cmd),
                      ("status", status_cmd), ("label", label_cmd), ("remove", remove_cmd),
                      ("phone", phone_cmd), ("check", check_cmd), ("cancel", cancel_cmd),
                      ("allow", allow_cmd), ("revoke", revoke_cmd), ("users", users_cmd),
                      ("health", health_cmd)]:
         app.add_handler(CommandHandler(name, fn, filters=private))
     app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & private, text_message))
     app.add_handler(MessageHandler(filters.COMMAND & private, unknown_command))
     app.add_error_handler(on_error)
     return app
     ```
   - `_post_init(app)`: open `Repository`; `now = lambda: datetime.now(UTC)`; upsert admin (`is_allowed=True, is_admin=True`); `http = make_http_client(settings)`; `notifier = TelegramNotifier(app.bot)`; build `ParcelService` and `Poller` with `CARRIERS`; store `Deps` in `bot_data["deps"]`; `app.job_queue.run_repeating(poll_job, interval=settings.poll_interval, first=FIRST_POLL_DELAY_SECONDS, name="poll")`; `await app.bot.set_my_commands(BOT_COMMANDS)`; log INFO `"bot started as @%s"` with `app.bot.username`.
   - `_post_shutdown(app)`: if deps exist → `await http.aclose()`, `await repo.close()`; log INFO.
   - `poll_job(context)` → `await get_deps(context).poller.run_cycle()`.
   - `on_error(update, context)`:
     - `telegram.error.Conflict` → log CRITICAL `"another bot instance is polling with this token"`; `context.bot_data["exit_code"] = 1`; `context.application.stop_running()`.
     - `NetworkError`/`TimedOut` → log WARNING, return.
     - Otherwise log ERROR with `exc_info=context.error`; if `update` is an `Update` with `effective_message` → try reply `ERROR_GENERIC`; admin alert `ALERT_ERROR` (`detail = type(err).__name__`) with `ERROR_ALERT_COOLDOWN` using meta key `alert:error` (skip if deps missing).
11. `__main__.py`:
    ```python
    def main() -> int:
        load_dotenv(Path.cwd() / ".env")
        try:
            settings = Settings.from_env(os.environ)
        except ConfigError as exc:
            _write_startup_error(Path(os.environ.get("LOG_DIR") or "logs"), str(exc))
            if sys.stderr is not None:
                print(exc, file=sys.stderr)
            return 2
        setup_logging(settings)
        log = logging.getLogger("vn_parcel_bot")
        try:
            with SingleInstanceLock(settings.db_path.parent / "bot.lock"):
                app = build_application(settings)
                app.run_polling(allowed_updates=Update.ALL_TYPES)
                return int(app.bot_data.get("exit_code", 0))
        except SingleInstanceError:
            log.warning("another instance is running; exiting")
            return 0
        except Exception:
            log.exception("fatal error")
            return 1

    if __name__ == "__main__":
        raise SystemExit(main())
    ```
    `_write_startup_error` creates the dir and appends `"<ISO time> <message>\n"` to `startup-error.log` (UTF-8). Load `.env` from the **working directory** only (never `find_dotenv`, which would find the repo `.env` during tests).

**Tests (write first):**

`tests/test_single_instance.py`
- `test_second_lock_fails_then_succeeds_after_release(tmp_path)`.
- `test_creates_parent_directory`.

`tests/test_bot_parsing.py`
- `test_track_args_none_when_empty`.
- `test_track_args_code_only` — `["SPXVN000000000001"]` → `("SPXVN000000000001", None)`.
- `test_track_args_code_with_phone` — `["840000000001", "1234"]` → `("840000000001", "1234")`.
- `test_track_args_spaced_code_not_mistaken_for_phone` — `["SPXVN", "0000", "0000", "0001"]` → `("SPXVN000000000001", None)`.
- `test_track_args_spaced_code_with_phone` — `["SPXVN", "000000000001", "1234"]` → code + `"1234"`.
- `test_ref_and_text` — `[]` → `None`; `["1"]` → `("1", None)`; `["1", "Áo", "khoác"]` → `("1", "Áo khoác")`.
- `test_route_phone_for_pending` — `("1234", True)` → `phone_for_pending`, `last4="1234"`.
- `test_route_codes_override_pending` — `("SPXVN000000000001", True)` → `codes`.
- `test_route_invalid_phone_when_pending` — `("12", True)` → `invalid_phone`.
- `test_route_unknown` — `("xin chào", False)` → `unknown`; `("1234", False)` → `unknown`.
- `test_route_multiple_codes` — two codes in order.

`tests/test_auth.py`
- `test_is_authorized_matrix` — admin without DB row ✔; allowed ✔; not allowed ✘; unknown ✘.
- `test_admin_only_blocks_non_admin` — `SimpleNamespace` update/context (`effective_user.id=2`, `effective_message.reply_text` async recorder, `bot_data={"settings": settings}`) → wrapped handler not called, reply contains `ADMIN_ONLY`.
- `test_admin_only_allows_admin`.

`tests/test_notifier.py`
- `test_send_uses_html_silent_and_no_preview` — fake bot records kwargs: `parse_mode == ParseMode.HTML`, `disable_notification is True`, `link_preview_options.is_disabled is True`.
- `test_forbidden_is_swallowed` — fake bot raises `telegram.error.Forbidden("blocked")` → no exception.
- `test_other_errors_propagate` — `RuntimeError` propagates.

`tests/test_app.py`
- `test_build_application_registers_handlers(settings)` — no network: group `-1` holds one `TypeHandler`; the set of `CommandHandler.commands` in group `0` equals `{start, help, track, list, status, label, remove, phone, check, cancel, allow, revoke, users, health}`; the last handler in group `0` is the unknown-command `MessageHandler`; `len(app.error_handlers) == 1`; `app.bot_data["settings"] is settings`.
- `test_build_application_with_proxy(settings)` — `dataclasses.replace(settings, telegram_proxy_url="socks5h://127.0.0.1:1080")` builds without error.
- `test_bot_commands_match_spec` — names in `BOT_COMMANDS` equal the 10 advertised commands.

`tests/test_main.py`
- `test_config_error_returns_2_and_writes_log(tmp_path, monkeypatch)` — `chdir(tmp_path)`; delete `TELEGRAM_BOT_TOKEN`, `ADMIN_TELEGRAM_ID`, `LOG_DIR`, `DB_PATH` from env → `main() == 2`; `tmp_path/"logs"/"startup-error.log"` exists and does not contain a token.
- `test_second_instance_returns_0(tmp_path, monkeypatch, valid_env)` — `chdir(tmp_path)`; set env; hold `SingleInstanceLock(tmp_path/"data"/"bot.lock")`; monkeypatch `vn_parcel_bot.__main__.build_application` to raise `AssertionError` → `main() == 0`.

**Verify:**
```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m ruff format --check .
.\.venv\Scripts\python -m pytest -q --cov=vn_parcel_bot --cov-report=term-missing
```
Then a **short live smoke run** (requires `.env`): start `.\.venv\Scripts\python -m vn_parcel_bot`, wait for `bot started as @…` in `logs\bot.log`, stop with Ctrl+C, confirm `bot stopped` logged and no traceback.

**Done when:** gates green; smoke run starts and stops cleanly; coverage for `tracking_codes`, `carriers`, `db`, `services` ≥ 85 %.

**Commit:** `feat: telegram bot layer, entry point, and single-instance lock`

---

## Prompt 11 — Live end-to-end run (interactive)

**Goal:** Prove acceptance scenarios 1–11 (§14) against real Telegram and real carriers, fixing any bug with a regression test first.

**Run interactively** (`agy -i` or Claude Code). The agent drives and checks logs/DB; **you** use Telegram on your phone, plus one family member's account (or a second account) for scenarios 1–2.

**Spec:** §3, §4, §6, §14.

**Preconditions:** Prompt 10 committed; `.env` filled; `probe_codes.local.txt` has at least one in-transit SPX and one in-transit J&T code (with digits).

**Create/modify:**
- Modify `src/vn_parcel_bot/db/repo.py` — add dev-support methods (and document them in §9.8 of `BUILD_PLAN.md` in the same commit):
  ```python
  async def parcels_by_code(self, tracking_number: str) -> list[Parcel]: ...
  async def delete_latest_event(self, parcel_id: int) -> TrackingEvent | None: ...   # most recent by event_time, id
  async def set_next_check(self, parcel_id: int, when: datetime, now: datetime) -> None: ...
  ```
- Create `scripts/dev_replay_last_event.py` — `python scripts/dev_replay_last_event.py <code>`: loads settings from `.env`, opens `Repository`, for every parcel with that code deletes its latest event and sets `next_check_at = now`; prints parcel id, masked code, and the removed event's local time (never the description).
- Add tests for the three repo methods to `tests/test_repo.py`.
- Create `tests/E2E_RESULTS.md` — table: scenario #, date/time, result (pass/fail), notes (no personal data, masked codes only).

**Procedure:**

1. Write the repo-method tests first, implement, gates green, commit `feat: dev support to replay tracking events`.
2. Human starts the bot in a separate terminal: `.\.venv\Scripts\python -m vn_parcel_bot`. Agent follows `logs\bot.log` (`Get-Content logs\bot.log -Tail 30`) after each step.
3. For each scenario 1–11 in §14, in order:
   - Tell the human exactly what to send (and from which account).
   - Human reports the bot's reply (text or screenshot).
   - Agent checks the reply against §17 wording, checks the log, and checks DB state with a short Python snippet using `Repository` (print counts/states only, masked codes).
   - Record the result row in `tests/E2E_RESULTS.md`.
4. Scenario 8 (update notification): run `.\.venv\Scripts\python scripts\dev_replay_last_event.py <code>`, then human sends `/check` (or waits one interval). Expect exactly one update message with that event; human sends `/check` again after the 5-minute cooldown → no new message.
5. On any failure:
   - Stop the bot (Ctrl+C in its terminal).
   - Reproduce the bug in a **unit test** (red), fix (green), run all gates.
   - Commit `fix: <short description>`.
   - Restart the bot and re-run the failed scenario and any earlier scenario the fix could affect.
6. When all 11 pass, stop the bot.

**Done when:** scenarios 1–11 recorded as pass; all fixes have regression tests; gates green.

**Commit:** `test: record live end-to-end results for scenarios 1-11`

---

## Prompt 12 — Windows auto-start and README

**Goal:** The bot starts automatically at logon, restarts on failure, and a human can operate it from the README alone.

**Spec:** §12, §10, §11.

**Preconditions:** Prompt 11 committed; the bot is **not** running.

**Create:** `scripts/run-bot.ps1`, `scripts/install-task.ps1`, `scripts/uninstall-task.ps1`, `scripts/status-bot.ps1`. **Rewrite:** `README.md`.

**Build:**

1. `scripts/run-bot.ps1`:
   ```powershell
   $ErrorActionPreference = "Stop"
   $root = Split-Path -Parent $PSScriptRoot
   Set-Location $root
   & (Join-Path $root ".venv\Scripts\python.exe") -m vn_parcel_bot
   exit $LASTEXITCODE
   ```
2. `scripts/install-task.ps1`:
   ```powershell
   param([string]$TaskName = "VN Parcel Bot")
   $ErrorActionPreference = "Stop"
   $root = Split-Path -Parent $PSScriptRoot
   $pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
   if (-not (Test-Path $pythonw)) { throw "Missing $pythonw - create the virtualenv first (see README)." }
   if (-not (Test-Path (Join-Path $root ".env"))) { throw "Missing .env in $root - copy .env.example and fill it." }
   $user = "$env:USERDOMAIN\$env:USERNAME"
   $action = New-ScheduledTaskAction -Execute $pythonw -Argument "-m vn_parcel_bot" -WorkingDirectory $root
   $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
   $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
       -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
       -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
   $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
   Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
       -Principal $principal -Force | Out-Null
   Start-ScheduledTask -TaskName $TaskName
   Start-Sleep -Seconds 5
   Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
   ```
3. `scripts/uninstall-task.ps1`:
   ```powershell
   param([string]$TaskName = "VN Parcel Bot")
   $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
   if ($null -eq $task) { Write-Output "Task '$TaskName' is not installed."; exit 0 }
   Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
   Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
   Write-Output "Removed task '$TaskName'."
   ```
4. `scripts/status-bot.ps1`:
   ```powershell
   param([string]$TaskName = "VN Parcel Bot")
   $root = Split-Path -Parent $PSScriptRoot
   $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
   if ($task) { $task | Get-ScheduledTaskInfo | Select-Object LastRunTime, LastTaskResult, NextRunTime; "State: $($task.State)" }
   else { "Task '$TaskName' not installed." }
   Get-CimInstance Win32_Process -Filter "Name like 'python%.exe'" |
       Where-Object { $_.CommandLine -match 'vn_parcel_bot' } |
       Select-Object ProcessId, CreationDate
   $log = Join-Path $root "logs\bot.log"
   if (Test-Path $log) { Get-Content $log -Tail 20 }
   $err = Join-Path $root "logs\startup-error.log"
   if (Test-Path $err) { "--- startup-error.log ---"; Get-Content $err -Tail 5 }
   ```
5. `README.md` sections (Vietnamese command names, English prose is fine):
   1. What it does (3 lines) and supported carriers.
   2. Requirements: Windows 10/11, Python 3.13, git; Telegram reachable (proxy note).
   3. Setup: BotFather (copy the Prompt 0 steps from `BUILD_PLAN.md`), `py -3.13 -m venv .venv`, `pip install -e .`, copy `.env.example` → `.env` with a table of variables (from §10.1), first foreground run with `scripts\run-bot.ps1`, `/start` from your account.
   4. Auto-start: `powershell -ExecutionPolicy Bypass -File scripts\install-task.ps1`; uninstall; status.
   5. Using the bot: the command table from §4.1 (user commands), the J&T 4-digit rule, quiet hours.
   6. Adding family: they send `/start` → forward you the ID → `/allow <id> <name>`; `/revoke`, `/users`.
   7. Operations: status, stop (`Stop-ScheduledTask "VN Parcel Bot"`), start, restart, update (`git pull`, `.\.venv\Scripts\python -m pip install -e .`, restart task), logs location and rotation, DB location, reset (stop task, delete `data\bot.sqlite3`).
   8. Troubleshooting: table from Appendix C of `BUILD_PLAN.md`.
   9. Maintenance: monthly `scripts\probe_carriers.py carriers`; what to do on `ALERT_CARRIER` (Appendix A prompt).
   10. Privacy: what is stored (Telegram id/name, codes, events, last 4 digits), where, retention (terminal parcels purged after 30 days).

**Verify (agent + human):**
```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-task.ps1
powershell -ExecutionPolicy Bypass -File scripts\status-bot.ps1
powershell -ExecutionPolicy Bypass -File scripts\install-task.ps1   # idempotent re-run
powershell -ExecutionPolicy Bypass -File scripts\uninstall-task.ps1
powershell -ExecutionPolicy Bypass -File scripts\status-bot.ps1     # no python process for vn_parcel_bot
powershell -ExecutionPolicy Bypass -File scripts\install-task.ps1
```
Expected: task `Running`; exactly one `pythonw.exe … vn_parcel_bot` process; `bot started as @…` in the log after each install; after uninstall no process remains. Human sends `/list` while the task runs → bot answers.

**Done when:** verify steps pass; README complete; the task is left installed and running.

**Commit:** `feat: windows auto-start scripts and operator README`

---

## Prompt 13 — Hardening drills and final review

**Goal:** Run the remaining acceptance scenarios (§14, 12–15), close any gap between the specification and the code, and tag v1.0.0.

**Run interactively.**

**Spec:** entire document; §12, §14.

**Preconditions:** Prompt 12 committed; the task is installed and running.

**Build / procedure:**

1. **Invalid token handling.** In `__main__.py`, catch `telegram.error.InvalidToken` around `build_application`/`run_polling`: write `"Telegram rejected the bot token"` to `startup-error.log`, log CRITICAL, return `2`. Test first in `tests/test_main.py`: `test_invalid_token_returns_2` (monkeypatch `build_application` to return an object whose `run_polling` raises `InvalidToken`; `bot_data` is a dict).
2. **Drill 12 — logon restart (human):** sign out and back in (or reboot). Within 1 min `status-bot.ps1` shows one process and a fresh `bot started` line. Send `/check` → no duplicate notifications for already-seen events.
3. **Drill 13 — network loss (human):** turn Wi-Fi off 15 min, then on. Expect WARNING lines for carrier `network` errors and PTB network errors, no crash, no user-facing error messages, normal operation after reconnect.
4. **Drill 13b — carrier alert:** with ≥3 active parcels of one carrier (use test codes), stop the task, set `HTTP_TIMEOUT_SECONDS=0.001` in `.env`, run `scripts\run-bot.ps1`, send `/check` → admin receives exactly one `ALERT_CARRIER`; `/check` again after cooldown → no second alert (6 h cooldown). Restore `.env`, stop the foreground bot, `Start-ScheduledTask "VN Parcel Bot"`.
5. **Drill 14 — second instance:** while the task runs, `scripts\run-bot.ps1` → exits within seconds with exit code 0 and log `another instance is running; exiting`.
6. **Drill 15 — token leak scan** (prints counts only, never the token):
   ```powershell
   $t = (Select-String -Path .env -Pattern '^TELEGRAM_BOT_TOKEN=(.+)$').Matches[0].Groups[1].Value
   (Select-String -Path logs\* -Pattern $t -SimpleMatch | Measure-Object).Count
   (git log -p --all | Select-String -Pattern $t -SimpleMatch | Measure-Object).Count
   Remove-Variable t
   ```
   Expected: `0` and `0`.
7. **Spec traceability review:** go through §3–§12 requirement by requirement. For each, name the implementing file and the test that covers it (write the mapping into `tests/E2E_RESULTS.md` under a "Traceability" heading). Any requirement without code or test → add the test (red), implement (green).
8. **Final quality pass:**
   ```powershell
   .\.venv\Scripts\python -m pytest -q --cov=vn_parcel_bot --cov-report=term-missing
   .\.venv\Scripts\python -m ruff check .
   .\.venv\Scripts\python -m ruff format --check .
   .\.venv\Scripts\python -m pip freeze --exclude-editable | Out-File -Encoding utf8 requirements.lock.txt
   ```
   Coverage ≥ 85 % for `tracking_codes`, `carriers`, `db`, `services`.
9. Record drills 12–15 in `tests/E2E_RESULTS.md`; tick every row in **Progress**.
10. After the commit: `git tag v1.0.0`.

**Done when:** drills 12–15 pass; traceability has no gaps; gates green; tag created. Restart the task if any drill stopped it.

**Commit:** `chore: hardening drills, traceability review, v1.0.0`

---

# Part 4 — Appendices

## Appendix A — Maintenance prompt: a carrier changed

Use when the admin receives `ALERT_CARRIER` repeatedly or `/status` shows stale data.

```text
Read BUILD_PLAN.md ("Standing rules" and Part 2 Specification) and tests/fixtures/FIXTURES.md.
The <spx|jt> carrier appears broken (admin alerts / parse errors in logs\bot.log).
1. Show the last 50 WARNING/ERROR lines for that carrier from logs\bot.log (masked codes only).
2. Run: .\.venv\Scripts\python scripts\probe_carriers.py carriers  (I have refreshed probe_codes.local.txt).
3. Compare the new raw captures with the committed fixtures and describe exactly what changed.
4. If a captcha, JS challenge, signed token, or login is now required: STOP and give me the Prompt 2 gate options.
5. Otherwise: update FIXTURES.md, replace the sanitized fixtures, update the carrier tests to the new facts (red),
   fix the parser/fetch (green), run all quality gates.
6. Stop-ScheduledTask "VN Parcel Bot"; Start-ScheduledTask "VN Parcel Bot"; ask me to send /check.
7. Commit "fix(<carrier>): adapt to tracking page change".
```

## Appendix B — Future prompt: add another carrier (template)

```text
Read BUILD_PLAN.md ("Standing rules" and Part 2 Specification).
Add carrier <NAME> (code "<code>") following the SPX/J&T pattern:
1. Update §5 (new subsection + detection regex, checking for overlap with existing patterns), §7 CHECK
   constraint (new migration 2 that rebuilds the parcels table CHECK), §9.7, §17 CARRIER_NAMES.
2. Live-probe with real codes exactly like Prompt 2 (GATE applies), capture sanitized fixtures.
3. TDD: tracking_codes detection tests, carrier parser/fetch tests, migration test (v1 DB upgrades to v2 with data intact).
4. Register in CARRIERS. Gates. Commit "feat: <NAME> carrier".
```

## Appendix C — Troubleshooting

| Symptom | Likely cause | Check | Fix |
|---|---|---|---|
| Bot never replies | Task not running / crashed | `scripts\status-bot.ps1`; `logs\startup-error.log` | Fix `.env`; `Start-ScheduledTask "VN Parcel Bot"` |
| `startup-error.log`: Invalid configuration | Missing/invalid `.env` value | The listed variables | Edit `.env`, restart task |
| `startup-error.log`: token rejected | Token revoked/typo | @BotFather `/token` | Update `TELEGRAM_BOT_TOKEN` |
| Log: `NetworkError` / `TimedOut` repeatedly | Telegram blocked or internet down | Prompt 0.3 commands | Set `TELEGRAM_PROXY_URL`, restart |
| Log: `another bot instance is polling` | Same token running elsewhere (other PC, a foreground run) | `status-bot.ps1`; other machines | Stop the other instance |
| Log: `another instance is running; exiting` | Normal when a second copy starts | – | Nothing |
| Admin gets `ALERT_CARRIER` | Carrier page/API changed or blocking | `probe_carriers.py carriers` | Appendix A prompt |
| J&T parcel stays "Chưa có thông tin" | Wrong 4 digits, or parcel not yet scanned | Try on jtexpress.vn with the same digits | `/remove` then `/track <mã> <4 số đúng>` |
| Updates arrive late | PC was asleep/off | Windows power settings | Sleep = Never when plugged in |
| No sound at night | Quiet hours (silent delivery) | `QUIET_HOURS` in `.env` | Change or set empty to disable |
| Family member gets 🔒 | Not allowlisted / revoked | `/users` | `/allow <id> <tên>` |
| `ZoneInfoNotFoundError` | `tzdata` missing | `pip show tzdata` | `pip install -e .` |

## Appendix D — Spec coverage map

| Spec section | Implemented in | Verified in |
|---|---|---|
| §3 Users and access | P6 (users table/repo), P10 (gate, admin) | P6, P10 tests; P11 scenarios 1–2 |
| §4.1 Commands | P10 handlers, P7 texts/formatting | P7, P10 tests; P11 scenarios 3–11 |
| §4.2 Plain-text routing | P10 `bot/parsing.py` | P10 tests; P11 scenarios 4, 7 |
| §4.3 Adding a parcel | P8 `ParcelService.add` | P8 tests; P11 scenarios 3–7 |
| §5.1–5.2 Carrier facts | P2 probe + fixtures | P2 gate; P4/P5 fixture tests |
| §5.3 Detection | P3 | P3 tests |
| §5.4 Fetch contract | P2 (http client), P4, P5 | P4, P5 tests |
| §5.5 Politeness | P9 | P9 pacing/grouping tests |
| §6 Polling and notifications | P9; schedule in P10 | P9 tests; P11 scenarios 8–9 |
| §7 Data model | P6 | P6 tests |
| §8–9 Architecture and interfaces | P1–P10 | Per-prompt tests; P13 traceability |
| §10 Configuration | P1 | P1 tests |
| §11 Logging, security, privacy | P1 (logging), P2 (sanitizing), P10 | P1 tests; P2 verify; P13 drill 15 |
| §12 Runtime on Windows | P10 (lock, exit codes), P12 (task), P13 (InvalidToken) | P10, P13 tests; P12 verify; P13 drills 12–14 |
| §13 Testing strategy | all prompts | quality gates on every prompt |
| §14 Acceptance scenarios | – | P11 (1–11), P13 (12–15) |
| §17 Text catalog | P7 `texts.py` | P7 tests; P11 wording checks |
