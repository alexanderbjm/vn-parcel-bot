# SPX order-info endpoint, screenshot → parcel, daily digests — design

Date: 2026-09-14 · Branch: `build/v1` (after `b632fc0`) · Status: approved in chat; Part C revised after a live spike (see §3)

## 1. Why

- **SPX is not tracking.** The bot calls `GET https://spx.vn/api/v2/fleet_order/tracking/search?sls_tracking_number=<code>`. For a real code that spx.vn's own page showed as out for delivery on 2026-09-14, that endpoint returned `{"retcode":0,"message":"","data":{}}`, the same answer as an unknown code, so every SPX parcel stays pending until it expires (BUILD_PLAN risk R1).
- **Screenshots.** The user wants to send an order screenshot and get the parcel added with its product name. agy added a first version in `b632fc0` (Claude Vision service, photo handler, tests); it reads codes but not the product name, defaults to an old model and shares the carriers' 15 s timeout.
- **Daily digests.** The user wants a Telegram summary of their orders at 07:00, 12:00, 19:00 and 22:00.

## 2. Decisions (from the chat)

| Topic | Decision |
|---|---|
| SPX | Use the endpoint spx.vn's tracking page itself loads the timeline from: `GET https://spx.vn/shipment/order/open/order/get_order_info?language_code=vi&spx_tn=<code>`. A plain request works (verified 2026-09-14). No browser, no signatures, no page-generated headers. If SPX starts blocking it, the bot backs off, alerts the admin and keeps sending the spx.vn link; no evasion. (Replaces the approved hidden-Edge plan; the user chose this on 2026-09-14.) |
| Image engine | Claude Haiku 4.5 through the Anthropic API; the user adds the key to `.env` |
| Order number only in a screenshot | Reply with the product name and ask for the "Thông tin vận chuyển" screen; store nothing |
| Instant updates | Unchanged (sent immediately, silent during quiet hours) |
| Digest content | Full list of active parcels every time, 🆕 on parcels with new events since the previous digest, parcels that finished since then shown once, nothing sent when there is nothing to show |
| Build order | Part C (SPX) → Part B (screenshots) → Part A (digests) |

Out of scope: headless browsers, forging SPX signatures, OCR without the API, a `/digest` command, per-user digest times, remembering order numbers or product names without a shipping code, combining album photos into one request, resizing large images.

## 3. Part C — SPX through the order-info endpoint

### How this was found (2026-09-14)

1. A throwaway headless-Edge spike loaded `https://spx.vn/track?<real code>` and logged the page's own XHR/fetch calls. The page did **not** call `fleet_order/tracking/search` for the real code; it loaded the timeline from `GET spx.vn/shipment/order/open/order/get_order_info` with `language_code` and `spx_tn`.
2. A plain `httpx` GET to that URL (the bot's normal headers, nothing from the page) returned `retcode 0` with 17 records, including the delivery that happened minutes earlier. An unknown code (`SPXVN000000000001`) returned `retcode 2`, `data {}`, message `…find [0]:get logistic order index map error`.
3. Playwright was installed only for the spike and has been removed again.

### Response shape (observed)

- `retcode` (int): `0` success; `2` for an unknown code.
- `data.sls_tracking_info.records[]`, newest first. Fields used:
  - `actual_time` (int, Unix seconds, UTC)
  - `description` (str; may contain doubled or leading spaces)
  - `tracking_code` (str, e.g. `F000` manifested, `F100` picked up, `F510` sorting centre, `F599` last-mile hub, `F600` out for delivery, `F980` delivered)
  - `milestone_code` (int: `1` preparing, `5` in transit, `6` out for delivery, `8` delivered) and `milestone_name` (str)
  - `display_flag` (int): `1` for the events spx.vn shows to the public, `0` for internal steps
  - `current_location.location_name` (str, often empty; usually already part of `description`)
- **Personal data in the same response, never read, stored, logged or put in fixtures:** `receiver_name`, `driver_phone_number`, `client_order_id`, `buyer_description`, `epod`, `current_location.full_address`, `lat`, `lng`, `next_location`.

### Components

- `carriers/spx.py`
  - `SPX_ORDER_INFO_URL = "https://spx.vn/shipment/order/open/order/get_order_info"`.
  - `parse_spx_response(payload, tracking_number)`:
    - Not a dict or no `retcode` → `parse` "unexpected payload".
    - `retcode` in `NOT_FOUND_RETCODES = (2,)` → not found. Any other non-zero `retcode` → `parse` `retcode=<n>`.
    - `data` missing/empty, `sls_tracking_info` missing, or `records` missing/empty → not found. `sls_tracking_info` not a dict or `records` not a list → `parse`.
    - Records with `display_flag != 1` are skipped. Each kept record must be a dict with an integer `actual_time` (not bool) and a non-empty `description` after whitespace collapsing, else `parse`.
    - Event: `time = datetime.fromtimestamp(actual_time, UTC)`; `description` whitespace-collapsed; `location` = collapsed `location_name` only when non-empty and not already contained in the description (case-insensitive); `raw_status = tracking_code`.
    - No kept records → not found.
    - Delivered: the latest kept record has `milestone_code == 8` or `tracking_code == "F980"`. Returned: not delivered and the latest kept record's `description`, `tracking_name` or `milestone_name` contains `return`, `hoàn hàng` or `trả hàng` (case-insensitive).
  - `SpxCarrier.fetch`: `request(http, "spx", "GET", SPX_ORDER_INFO_URL, params={"language_code": "vi", "spx_tn": code})`, then `parse_spx_response(json_body(...), code)`. Existing `request`/`json_body` mapping applies (403/429 and challenge pages → `blocked`, other non-2xx → `http_status`, transport errors → `network`, HTML instead of JSON → `blocked`).
  - Removed: `SPX_TRACKING_URL`, `SPX_SIGNING_SECRET`, `sign_spx_code`, the `secret`/`clock` constructor arguments and their tests.
- `tests/fixtures/spx/`: replaced by synthetic files in the observed shape (placeholder personal fields such as `"receiver_name": "N***A"` so tests can prove they are ignored); `FIXTURES.md` SPX section rewritten.
- `scripts/probe_carriers.py`: SPX request switched to the new URL; `--spx-secret` removed; SPX event count path `data.sls_tracking_info.records`.

### Tests

Parser: in transit, delivered (by tracking code and by milestone), returned marker, not found (retcode 2, empty data, empty records, only hidden records), hidden records skipped, whitespace collapsed, location kept only when not in the description, personal fields never appear in events, malformed payloads and records, unknown retcode. Fetch: query parameters, error mapping (403, 500, captcha HTML, transport error). Probe script: namespace without `spx_secret`.

## 4. Part B — Screenshot → parcel (building on `b632fc0`)

### Changes to agy's code

- `config.py`
  - `ANTHROPIC_MODEL` default `claude-haiku-4-5-20251001`.
  - New `VISION_TIMEOUT_SECONDS` (default 60, allowed 10–180).
  - Keep agy's uncommitted optional `ANTHROPIC_WORKSPACE_ID`, sent as the `anthropic-workspace-id` header (needed for organization-level keys; the user's current key does not need it).
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
    2. Pick the largest photo, or an image document. A document whose MIME type is not `image/jpeg`, `image/png`, `image/webp` or `image/gif`, or whose `file_size` is over `VISION_MAX_IMAGE_BYTES` (5 MB), gets `VISION_UNSUPPORTED_IMAGE` without downloading.
    3. Photos from the same user are processed one at a time (a per-user lock in `bot_data`). Each photo still gets its own reply.
    4. Send "typing", download, call the service. Error → `VISION_ERROR` (generic, no detail).
    5. Shipping codes found → one code: the normal single-add flow with `label=product_name`; several: the multi-add flow, each with the label. Every reply starts with `VISION_DETECTED_HEADER` and, when known, `VISION_PRODUCT`.
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

- `ANTHROPIC_API_KEY` in `.env` (Claude never reads or prints it). On 2026-09-14 the key was accepted but the account had no credit ("Your credit balance is too low"); the user adds credit under Plans & Billing.
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
4. Restart the "VN Parcel Bot" task safely: stop the task, stop leftover bot processes and wait for them to exit, start the task, confirm "bot started" in the log.
5. Live check: Part C with the real SPX code through the probe script (`probe_codes.local.txt`, never committed) and the next poll; Part B once the account has credit and the model line is fixed; Part A at the next digest time.

## 7. Risks

| Risk | Mitigation |
|---|---|
| SPX blocks or changes the order-info endpoint | `blocked`/`http_status`/`parse` errors surface through the existing backoff and admin alerts; replies keep the spx.vn link; no evasion. |
| `retcode 2` also covers errors other than "unknown code" | An affected parcel stays pending and expires after 7 days, as before; the probe script shows the message for investigation. |
| The response carries personal data | The parser reads only whitelisted fields; fixtures use placeholders; raw probe captures stay under the git-ignored `_raw` folder. |
| Vision misreads a code | The code still goes through normal detection and carrier lookups; wrong codes end as pending/expired or unknown replies. |
| API cost | Haiku 4.5, one request per photo, `max_tokens` 1024. |

## 8. Review notes (agy, Gemini 3.1 Pro, 2026-09-14)

| # | Finding | Outcome |
|---|---|---|
| 1 | Digest `since` set after sending can skip events saved mid-digest | Accepted: `cutoff` taken before queries, stored after a successful send (§5) |
| 2 | Hard-killed task can orphan Edge | No longer applies: Part C uses no browser |
| 3 | Product name lost when a screenshot has only an order number | Not adopted: the user chose to store nothing (§2) |
| 4 | Full-list digests repeat on quiet days | Not adopted: the user chose the full list over "only when something changed" (§2) |
| 5 | Anthropic image size/type limits | Accepted: type and 5 MB checks before download (§4) |
| 6 | Albums trigger parallel requests and replies | Partly: per-user sequential processing; one reply per photo kept (§4) |
| 7 | Idle close racing a new lookup | No longer applies: Part C uses no browser |
| 8 | `claude-haiku-4-5-20251001` "may be invalid" | Rejected: it is the current Haiku 4.5 model ID |
