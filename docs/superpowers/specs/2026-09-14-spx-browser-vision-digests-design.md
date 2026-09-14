# SPX via hidden Edge, screenshot → parcel, daily digests — design

Date: 2026-09-14 · Branch: `build/v1` (after `b632fc0`) · Status: approved in chat, reviewed by agy, waiting for the user's spec review

## 1. Why

- **SPX is not tracking.** A live check on 2026-09-14 showed spx.vn's own page with a full timeline for a real code (out for delivery), while the bot's direct `GET /api/v2/fleet_order/tracking/search` from the same PC returned `{"retcode":0,"message":"","data":{}}`, the same answer as an unknown code. spx.vn's page signs the request in its own script; the bot cannot, so every SPX parcel stays pending until it expires (BUILD_PLAN risk R1).
- **Screenshots.** The user wants to send an order screenshot and get the parcel added with its product name. agy added a first version in `b632fc0` (Claude Vision service, photo handler, tests); it reads codes but not the product name, defaults to an old model and shares the carriers' 15 s timeout.
- **Daily digests.** The user wants a Telegram summary of their orders at 07:00, 12:00, 19:00 and 22:00.

## 2. Decisions (from the chat)

| Topic | Decision |
|---|---|
| SPX | Read spx.vn's tracking page in a hidden Edge on this PC. If SPX blocks or shows a captcha, stop and fall back to the link. No secret extraction, no signature forging, no user-agent spoofing. |
| Image engine | Claude Haiku 4.5 through the Anthropic API; the user adds the key to `.env` |
| Order number only in a screenshot | Reply with the product name and ask for the "Thông tin vận chuyển" screen; store nothing |
| Instant updates | Unchanged (sent immediately, silent during quiet hours) |
| Digest content | Full list of active parcels every time, 🆕 on parcels with new events since the previous digest, parcels that finished since then shown once, nothing sent when there is nothing to show |
| Build order | Part C (SPX) → Part B (screenshots) → Part A (digests) |

Out of scope: forging SPX signatures, other carriers through the browser, OCR without the API, a `/digest` command, per-user digest times, remembering order numbers or product names without a shipping code, combining album photos into one request, resizing large images.

## 3. Part C — SPX through hidden Edge

### Components

- `carriers/spx_page.py` (new)
  - `class SpxPageSource(Protocol)`: `async def tracking_payload(self, code: str) -> object` and `async def aclose(self) -> None`.
  - `class EdgeSpxPageSource` implements it with Playwright (`playwright.async_api`):
    - Starts lazily on the first lookup: `async_playwright().start()`, then `chromium.launch(channel=settings.spx_browser_channel, headless=True)`. Default channel `msedge` uses the installed Edge; no `playwright install` download. No `--no-sandbox` or other flags that weaken the browser.
    - Each lookup uses a fresh `browser.new_context(locale="vi-VN")` (no persistent profile, no user cookies) and closes it afterwards.
    - `async with page.expect_response(match, timeout=SPX_PAGE_TIMEOUT)` around `page.goto(f"https://spx.vn/track?{quote(code, safe='')}")`, where `match` accepts a GET response whose URL path ends with `/api/v2/fleet_order/tracking/search`. Returns `await response.json()`.
    - One `asyncio.Lock` guards lookups, browser start and browser close. The idle timer is cancelled at the start of each lookup (inside the lock) and re-armed at its end; when it fires it takes the lock and closes the browser only if no lookup ran since it was armed. A lookup that finds the browser disconnected (`TargetClosedError`, `browser.is_connected()` false) starts a new one once and retries that lookup once.
    - Orphan cleanup: on first start, and from `scripts/run-bot.ps1` / the restart procedure, stop `msedge.exe` processes whose command line contains Playwright's temporary profile marker (`playwright_chromiumdev_profile-`) and `--remote-debugging-pipe`. The user's own Edge windows never match.
    - Error mapping (all `CarrierError("spx", …)`):
      - Response status 403/429 → `blocked`; other non-2xx → `http_status`.
      - No matching response before the timeout: if the page text contains a challenge word (`looks_like_challenge`) → `blocked` "challenge page"; else `network` "timeout".
      - Body not JSON → `parse` "invalid json".
      - Playwright launch failure (Edge missing, driver error, no desktop session) → `network` "browser unavailable", logged with the exception type only.
- `carriers/spx.py`
  - `SpxCarrier(source: SpxPageSource)`; `fetch` calls `source.tracking_payload(code)` and returns `parse_spx_response(payload, code)` (parser unchanged).
  - Removed: the direct request, `SPX_TRACKING_URL`, `SPX_SIGNING_SECRET`, `sign_spx_code` and their tests.
- `carriers/__init__.py`: `build_carriers(settings) -> dict[CarrierCode, Carrier]` creates the SPX source once; users of `CARRIERS` switch to it. `app._post_shutdown` awaits `aclose()` on carriers that have it.
- `scripts/probe_carriers.py`: the `spx` row goes through `EdgeSpxPageSource`; `--spx-secret` is removed.

### Settings and constants

- `SPX_BROWSER_CHANNEL` (default `msedge`; allowed `msedge`, `chrome`).
- `SPX_PAGE_TIMEOUT = 30 s`, `SPX_BROWSER_IDLE_CLOSE = 5 min` in `constants.py`.
- Dependency: `playwright` added to `pyproject.toml`.

### Behaviour

- Poller pacing, backoff, carrier failure alerts and link replies stay as they are; a `blocked` SPX error therefore backs off, alerts the admin after 5 failures, and add replies still carry the spx.vn and 17TRACK links.
- Adding an SPX code now waits for the page (typically 5–10 s); the handler sends the Telegram "typing" action first.
- Resource use: one Edge process tree while lookups run, closed after 5 idle minutes.
- The scheduled task runs in the user's logon session; if Edge cannot start there, lookups fail as `network` "browser unavailable" and the admin is alerted.

### Tests

- Unit: `SpxCarrier` with a fake `SpxPageSource` returning the existing SPX fixtures (in transit, delivered, not found, retcode ≠ 0) and raising each `CarrierError`.
- `EdgeSpxPageSource` with fake Playwright objects: response status mapping, timeout with and without challenge text, invalid JSON, launch failure, idle close, idle timer firing during a lookup, disconnected browser restarted once, orphan-process matching (command-line predicate only).
- No test starts a real browser. Live check: `python scripts/probe_carriers.py carriers --parse` with the real code kept in `probe_codes.local.txt` (never committed).

## 4. Part B — Screenshot → parcel (building on `b632fc0`)

### Changes to agy's code

- `config.py`
  - `ANTHROPIC_MODEL` default `claude-haiku-4-5-20251001`.
  - New `VISION_TIMEOUT_SECONDS` (default 60, allowed 10–180).
  - Keep agy's uncommitted optional `ANTHROPIC_WORKSPACE_ID`, sent as the `anthropic-workspace-id` header. The live key check on 2026-09-14 got `invalid_request_error`: "This API key is not scoped to a workspace, so this request must include the anthropic-workspace-id header".
- `services/vision.py`
  - The prompt also asks for `product_names` (list of item names as shown).
  - `VisionResult` gains `product_name: str | None`: the first name, whitespace-collapsed, with ` +N` when N more items exist, cut to `MAX_LABEL_LENGTH` (40).
  - Requests use `settings.vision_timeout_seconds`. The service requires the shared `httpx.AsyncClient` (no private client that is never closed).
  - `error` becomes a short code: `timeout`, `http_status`, `network`, `invalid_response`. Details go to the log (status code, exception type); no response bodies, image data or product names are logged.
- `services/parcels.py`: `add(user, raw_code, phone_last4=None, label=None)`. A label is stored on a new parcel, and set on a duplicate parcel only if it has no label. Outcomes carry the refreshed parcel.
- `bot/handlers_user.py`
  - Pending phone state becomes `{"code": str, "label": str | None}`; the 4-digit reply passes the label on.
  - `photo_message`:
    1. Not configured → `VISION_NOT_CONFIGURED`.
    2. Pick the largest photo, or an image document. A document whose MIME type is not `image/jpeg`, `image/png`, `image/webp` or `image/gif`, or whose `file_size` is over `VISION_MAX_IMAGE_BYTES` (5 MB), gets `VISION_UNSUPPORTED_IMAGE` without downloading. Telegram photos are always JPEG and small.
    3. Photos from the same user are processed one at a time (a per-user lock in `bot_data`), so albums and quick resends don't race on the pending-phone state. Each photo still gets its own reply.
    4. Send "typing", download, call the service. Error → `VISION_ERROR` (generic, no detail).
    5. Shipping codes found → one code: the normal single-add flow with `label=product_name`; several: the multi-add flow (`NEEDS_PHONE_MULTI` for codes that need digits), each with the label. Every reply starts with `VISION_DETECTED_HEADER` and, when known, `VISION_PRODUCT`.
    6. No shipping code but an order number → `VISION_ORDER_ONLY` with the product name (when known) and the order number; nothing stored.
    7. Nothing → `VISION_NO_DATA`.
    - Phone digits: from the screenshot, else a 4-digit word in the caption (agy's behaviour).
- `constants.py`: `VISION_MAX_IMAGE_BYTES = 5 * 1024 * 1024`.
- `texts.py`:
  - `VISION_PRODUCT = "• Sản phẩm: <b>{name}</b>"`
  - `VISION_ERROR = "⚠️ Không phân tích được hình ảnh lúc này. Bạn thử lại sau hoặc gửi mã vận đơn trực tiếp nhé."`
  - `VISION_UNSUPPORTED_IMAGE = "📷 Ảnh này quá lớn hoặc không đúng định dạng. Bạn gửi lại dưới dạng ảnh (không phải tệp) nhé."`
  - `VISION_ORDER_ONLY` gains an optional product line.
  - `HELP` gains "• Gửi ảnh chụp đơn hàng – mình tự đọc mã vận đơn và tên sản phẩm".

### Privacy

Screenshots go to Anthropic's API only; they are not written to disk. Logs keep masked codes only.

### Tests

agy's `tests/test_vision.py` and `tests/test_photo_handler.py` are extended: product name (single, several, long, missing), model default and timeout, workspace header (sent when set, absent otherwise), error codes never reaching the chat, label on new/duplicate/pending-phone parcels, order-only reply stores nothing, unsupported or oversized documents rejected without download, per-user sequential processing.

### Setup (user)

- The user creates an Anthropic API key and adds `ANTHROPIC_API_KEY=` to `.env`; Claude never reads or prints it. Without it the bot answers photos with `VISION_NOT_CONFIGURED`.
- The key must be workspace-scoped (created inside a workspace in the Anthropic Console), or `.env` must also set `ANTHROPIC_WORKSPACE_ID`. The key added on 2026-09-14 is organization-level and needs one of the two.
- `.env` currently has `ANTHROPIC_MODEL=claude-3-5-haiku-20241022`, which overrides the default; it must become `claude-haiku-4-5-20251001` or be removed.

## 5. Part A — Daily digests

### Components

- `config.py`: `DIGEST_TIMES` (default `07:00,12:00,19:00,22:00`; comma-separated `HH:MM`, de-duplicated and sorted; empty disables digests).
- `db/repo.py`: `parcel_ids_with_events_since(user_id, since) -> set[int]` (events whose `created_at >= since`).
- `services/digest.py` (new): `DigestService(repo, notifier, settings, now)`.
  - `async def send_all() -> int`: `cutoff = now()` is taken once, before any query. For every allowed user, build and send; returns messages sent.
  - `async def build(user_id, cutoff) -> str | None`:
    - `since` = meta `digest:last:<user_id>`, or `cutoff - 24 h` if absent.
    - Parcels = `repo.list_parcels(user_id, terminal_since=since)`: active parcels plus terminal parcels (`delivered`, `returned`, `expired`, `stale`) with `updated_at >= since`, in `created_at` order (existing query, no change).
    - None → `None` (nothing sent).
    - Each line uses the `/list` item layout plus `DIGEST_NEW_MARK` when the parcel id is in `parcel_ids_with_events_since(user_id, since)` or the parcel is terminal (it can only appear because it finished after `since`).
  - After a successful send, meta `digest:last:<user_id>` = `cutoff` (not the time the send finished), so an event saved by the poller while the digest was being built or sent is included next time. A failed send leaves the meta unchanged; a user who blocked the bot (`Forbidden`, logged by the notifier) counts as sent.
  - Messages are sent with sound (`silent=False`), through `truncate_message`.
- `bot/app.py`: one `job_queue.run_daily(digest_job, time=time(h, m, tzinfo=settings.tz))` per configured time. A slot missed while the bot was down is skipped; the next digest covers everything since the last one sent.
- `texts.py`: `DIGEST_HEADER = "🗓 <b>Tóm tắt đơn hàng</b> · {time}"`, `DIGEST_NEW_MARK = " 🆕"`, `DIGEST_FOOTER = "Đang theo dõi {active} đơn"`, `DIGEST_FOOTER_FINISHED = " · {finished} đơn vừa kết thúc"`.

### Tests

Config parsing (default, custom, empty, invalid, duplicates); `build` with a fake clock (first digest window, 🆕 from events, finished parcels shown once then dropped, nothing to show → `None`); an event inserted between `cutoff` and the end of the send appears in the next digest; a failed send keeps the previous `since`; `send_all` skips blocked users and sends with sound; four jobs registered at the right local times.

## 6. Rollout per part

1. Tests first, then code; `ruff check`, `ruff format --check`, full `pytest`.
2. Update `BUILD_PLAN.md` Part 2 (version 1.3) and regenerate `SPEC.md`.
3. Commit on `build/v1`.
4. Restart the "VN Parcel Bot" task safely: stop the task, stop leftover bot processes and Playwright Edge processes and wait for them to exit, start the task, confirm "bot started" in the log.
5. Live check: Part C with the real SPX code through the probe script and `/check`; Part B once the key is workspace-scoped (or the workspace ID is set) and the model line is fixed; Part A at the next digest time.

## 7. Risks

| Risk | Mitigation |
|---|---|
| SPX blocks headless Edge or adds a captcha | Lookup fails as `blocked`, backoff and admin alert; replies keep the spx.vn link; no evasion. The user can then choose link-only. |
| spx.vn changes its API path or response | Timeout/parse errors surface through the existing carrier alerts; the parser and path live in one place. |
| An Edge update breaks Playwright's `msedge` channel | Launch failure maps to `network` "browser unavailable" with an admin alert; update the `playwright` package. |
| The bot is killed mid-lookup and leaves Edge running | Orphan cleanup on first browser start and in the restart procedure (Playwright profile marker only). |
| Vision misreads a code | The code still goes through normal detection and carrier lookups; wrong codes end as pending/expired or unknown replies. |
| API cost | Haiku 4.5, one request per photo, `max_tokens` 1024. |

## 8. Review notes (agy, Gemini 3.1 Pro, 2026-09-14)

| # | Finding | Outcome |
|---|---|---|
| 1 | Digest `since` set after sending can skip events saved mid-digest | Accepted: `cutoff` taken before queries, stored after a successful send (§5) |
| 2 | Hard-killed task can orphan Edge; suggested `--no-sandbox`, `--disable-gpu` | Cleanup accepted (§3); sandbox-weakening flags rejected |
| 3 | Product name lost when a screenshot has only an order number | Not adopted: the user chose to store nothing (§2) |
| 4 | Full-list digests repeat on quiet days | Not adopted: the user chose the full list over "only when something changed" (§2) |
| 5 | Anthropic image size/type limits | Accepted: type and 5 MB checks before download (§4) |
| 6 | Albums trigger parallel requests and replies | Partly: per-user sequential processing; one reply per photo kept (§4) |
| 7 | Idle close racing a new lookup | Accepted: lock-guarded close and one restart on a disconnected browser (§3) |
| 8 | `claude-haiku-4-5-20251001` "may be invalid" | Rejected: it is the current Haiku 4.5 model ID |
