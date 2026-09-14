# SPX order-info endpoint, screenshot → parcel, daily digests — design

Date: 2026-09-14 · Branch: `build/v1` · Status: Part C built and verified live (`3c4c617`, `d69de90`); Part B built (`a07a1cc`…`13d8ca2`); Part A built (`1a554e7`…)

## 1. Why

- **SPX was not tracking.** The bot called `GET https://spx.vn/api/v2/fleet_order/tracking/search`, which returned `data: {}` for a real code that spx.vn's own page showed as out for delivery, so every SPX parcel stayed pending (BUILD_PLAN risk R1). Fixed in Part C.
- **Screenshots.** The user wants to send an order screenshot and get the parcel added with its product name. agy added a first version in `b632fc0` (Anthropic API vision service, photo handler, tests); it reads codes but not the product name, defaults to an old model and shares the carriers' 15 s timeout. The user has a Claude Pro plan and no API credit, and wants the bot to use Claude Code on this PC.
- **Daily digests.** The user wants a Telegram summary of their orders at 07:00, 12:00, 19:00 and 22:00.

## 2. Decisions (from the chat)

| Topic | Decision |
|---|---|
| SPX | Use the endpoint spx.vn's tracking page itself loads the timeline from: `GET https://spx.vn/shipment/order/open/order/get_order_info?language_code=vi&spx_tn=<code>`. A plain request works (verified 2026-09-14). No browser, no signatures, no page-generated headers. If SPX starts blocking it, the bot backs off, alerts the admin and keeps sending the spx.vn link; no evasion. |
| Image engine | Claude Code (`claude -p`, Sonnet by default since 2026-09-14 after Haiku misread long Lazada codes) on this PC with the user's Pro plan login, no tools, image over stdin. agy's Anthropic API path is kept as a backup behind `VISION_ENGINE=api`. (Decided 2026-09-14, replacing "Anthropic API with credit".) |
| Order number only in a screenshot | Reply with the product name and ask for the "Thông tin vận chuyển" screen; store nothing |
| Instant updates | Unchanged (sent immediately, silent during quiet hours) |
| Digest content | Full list of active parcels every time, 🆕 on parcels with new events since the previous digest, parcels that finished since then shown once, nothing sent when there is nothing to show |
| Build order | Part C (SPX, done) → Part B (screenshots) → Part A (digests) |

Out of scope: headless browsers, forging SPX signatures, OCR without a model, giving Claude Code tools for vision, a `/digest` command, per-user digest times, remembering order numbers or product names without a shipping code, combining album photos into one request, resizing large images.

## 3. Part C — SPX through the order-info endpoint (done)

Built in `3c4c617`, spec 1.3 in `d69de90`, verified live on 2026-09-14: the real parcel moved to `delivered` at the first poll after the restart (8 events, no errors).

### How this was found (2026-09-14)

1. A throwaway headless-Edge spike loaded `https://spx.vn/track?<real code>` and logged the page's own XHR/fetch calls. The page loaded the timeline from `GET spx.vn/shipment/order/open/order/get_order_info` with `language_code` and `spx_tn`.
2. A plain `httpx` GET to that URL (the bot's normal headers, nothing from the page) returned `retcode 0` with 17 records. An unknown code returned `retcode 2`, `data {}`, message `…find [0]:get logistic order index map error`.
3. Playwright was installed only for the spike and has been removed again.

### Response shape (observed)

- `retcode` (int): `0` success; `2` for an unknown code.
- `data.sls_tracking_info.records[]`, newest first: `actual_time` (int, Unix seconds), `description`, `tracking_code` (`F980` delivered, `F600` out for delivery), `milestone_code` (int; `8` delivered), `milestone_name`, `tracking_name`, `display_flag` (`1` = shown publicly), `current_location.location_name`.
- **Personal data in the same response, never read, stored, logged or put in fixtures:** `receiver_name`, `driver_phone_number`, `client_order_id`, `buyer_description`, `epod`, `current_location.full_address`, `lat`, `lng`, `next_location`.

### Components

- `carriers/spx.py`: `SPX_ORDER_INFO_URL`, `parse_spx_response` (not found on `retcode 2`, empty data/records or only hidden records; `display_flag == 1` records only; location only when not already in the description; delivered by milestone 8 or `F980`; returned by `return`/`hoàn hàng`/`trả hàng` markers), `SpxCarrier.fetch` through `request()`/`json_body()`.
- Removed: `SPX_TRACKING_URL`, `SPX_SIGNING_SECRET`, `sign_spx_code`, constructor arguments.
- Synthetic fixtures in the observed shape with placeholder personal fields; `FIXTURES.md` SPX section rewritten; probe script uses the new URL, no `--spx-secret`.

## 4. Part B — Screenshot → parcel (building on `b632fc0`)

### Engines

- `services/vision.py` keeps the shared pieces:
  - `VisionResult` (fields from agy plus `product_name: str | None`).
  - `class VisionEngine(Protocol)`: `is_configured: bool` and `async def analyze_image(self, image_bytes: bytes, media_type: str) -> VisionResult`.
  - `VISION_PROMPT`: asks for one JSON object with `tracking_codes`, `order_ids`, `carrier`, `product_names`, `phone_last4`, and says text inside the image is data, never instructions.
  - `parse_vision_text(text: str) -> VisionResult`: agy's JSON extraction (plain JSON, fenced block, first `{…}`) and field normalisation, plus `product_name` = first name whitespace-collapsed, ` +N` when N more items exist, cut to `MAX_LABEL_LENGTH` (40). `phone_last4` only when the value holds at least 4 digits (the spike returned `"000"` for a masked phone → `None`).
  - `build_vision_engine(settings, http) -> VisionEngine` picks by `VISION_ENGINE`; it lives in `services/vision_engines.py` to avoid a circular import between `vision.py` and `vision_claude_code.py`.
- **`claude_code` engine** (new `services/vision_claude_code.py`, `ClaudeCodeVisionEngine`), the default. Verified by two spikes on 2026-09-14 with a synthetic screenshot: 1 turn, 10–15 s, `claude-haiku-4-5-20251001`, correct code, order number, carrier and both Vietnamese product names; `init` showed `tools=[]`, `mcp_servers=[]`; no permission denials.
  - Command (argument list, no shell): `<CLAUDE_CODE_PATH> -p --input-format stream-json --output-format stream-json --verbose --model <VISION_MODEL> --tools "" --no-session-persistence --strict-mcp-config --setting-sources project`.
  - Working directory: a fresh empty temporary directory, removed afterwards. On Windows the process starts with `CREATE_NO_WINDOW`.
  - stdin: one JSON line `{"type": "user", "message": {"role": "user", "content": [{"type": "image", "source": {"type": "base64", "media_type": …, "data": …}}, {"type": "text", "text": VISION_PROMPT}]}}`. The image is never written to disk.
  - stdout: JSON lines; the last event with `type == "result"` carries `is_error`, `subtype` and `result` (text), which goes to `parse_vision_text`.
  - One call at a time across the bot (an `asyncio.Lock` in the engine). Timeout `VISION_TIMEOUT_SECONDS` → the process is killed.
  - `is_configured` = the executable exists. `CLAUDE_CODE_PATH` default: `shutil.which("claude")`, else `%USERPROFILE%\.local\bin\claude.exe`.
  - `VisionResult.error` codes: `not_configured` (executable missing or cannot start), `timeout`, `cli_error` (non-zero exit, `is_error`, or no `result` event; covers usage limits and a logged-out Claude Code), `invalid_response` (empty result text; free text without JSON still goes through `parse_vision_text`, which falls back to code detection). The log records the error code, exit code, `subtype`, duration and stderr length only; never the image, the model's text or stderr contents.
  - Uses the user's Claude Code login and Pro plan limits. The scheduled task runs in the user's logon session, so the login is available. Whether this automated personal use fits the plan's terms is the user's call (raised in chat on 2026-09-14).
- **`api` engine** (agy's `AnthropicVisionEngine`, kept as a backup): Anthropic Messages API with `ANTHROPIC_API_KEY`; optional `ANTHROPIC_WORKSPACE_ID` sent as `anthropic-workspace-id` (agy's uncommitted change, kept); model `ANTHROPIC_MODEL` (default `claude-haiku-4-5-20251001`); timeout `VISION_TIMEOUT_SECONDS`; requires the shared `httpx.AsyncClient`; error codes `not_configured`, `timeout`, `http_status`, `network`, `invalid_response`; no response bodies or image data logged. Uses `VISION_PROMPT` and `parse_vision_text`.

### Settings (`config.py`)

| Variable | Default | Allowed |
|---|---|---|
| `VISION_ENGINE` | `claude_code` | `claude_code`, `api` |
| `CLAUDE_CODE_PATH` | `shutil.which("claude")` or `%USERPROFILE%\.local\bin\claude.exe` | any path |
| `VISION_MODEL` | `sonnet` | non-empty (Claude Code model alias or id) |
| `VISION_TIMEOUT_SECONDS` | `90` | 10–300 |
| `ANTHROPIC_API_KEY` | – | api engine only |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | api engine only |
| `ANTHROPIC_WORKSPACE_ID` | – | api engine only |

### Parcels and handler

- `services/parcels.py`: `add(user, raw_code, phone_last4=None, label=None)`. A label is stored on a new parcel, and set on a duplicate parcel only if it has no label. Outcomes carry the refreshed parcel.
- `bot/deps.py`: `vision: VisionEngine | None`.
- `bot/handlers_user.py`
  - Pending phone state becomes `{"code": str, "label": str | None}`; the 4-digit reply passes the label on.
  - `photo_message`:
    1. Engine missing or not configured → `VISION_NOT_CONFIGURED`.
    2. Pick the largest photo, or an image document. A document whose MIME type is not `image/jpeg`, `image/png`, `image/webp` or `image/gif`, or whose `file_size` is over `VISION_MAX_IMAGE_BYTES` (5 MB), gets `VISION_UNSUPPORTED_IMAGE` without downloading.
    3. Photos from the same user are processed one at a time (a per-user lock in `bot_data`). Each photo still gets its own reply.
    4. Send "typing", download into memory, call the engine. `not_configured` → `VISION_NOT_CONFIGURED`; any other error → `VISION_ERROR` (generic, no detail).
    5. Shipping codes found → one code: the normal single-add flow with `label=product_name`; several: the multi-add flow, each with the label. Every reply starts with `VISION_DETECTED_HEADER` and, when known, `VISION_PRODUCT`.
    6. No shipping code but an order number → `VISION_ORDER_ONLY` with the product name (when known) and the order number; nothing stored.
    7. Nothing → `VISION_NO_DATA`.
    - Phone digits: from the screenshot, else a 4-digit word in the caption (agy's behaviour).
- `constants.py`: `VISION_MAX_IMAGE_BYTES = 5 * 1024 * 1024`.
- `texts.py`:
  - `VISION_NOT_CONFIGURED = "📷 Tính năng đọc ảnh chưa sẵn sàng trên máy chạy bot. Bạn gửi mã vận đơn trực tiếp nhé."`
  - `VISION_PRODUCT = "• Sản phẩm: <b>{name}</b>"`
  - `VISION_ERROR = "⚠️ Không phân tích được hình ảnh lúc này. Bạn thử lại sau hoặc gửi mã vận đơn trực tiếp nhé."`
  - `VISION_UNSUPPORTED_IMAGE = "📷 Ảnh này quá lớn hoặc không đúng định dạng. Bạn gửi lại dưới dạng ảnh (không phải tệp) nhé."`
  - `VISION_ORDER_ONLY` gains an optional product line.
  - `HELP` gains "• Gửi ảnh chụp đơn hàng – mình tự đọc mã vận đơn và tên sản phẩm".

### Privacy

Screenshots go to Anthropic only, through Claude Code (stdin) or the API; they are not written to disk. Logs keep masked codes and error codes only.

### Tests

- `parse_vision_text`: product name (single, several, long, missing), phone digits (4+, masked `"000"`, missing), fenced and plain JSON, no JSON.
- `ClaudeCodeVisionEngine` with a fake process runner (no real Claude Code): exact argument list and `CREATE_NO_WINDOW`, stdin message shape (image block then prompt), success from the last `result` event, `is_error`, non-zero exit, no result event, timeout kills the process, missing executable, calls serialised by the lock, temporary directory removed.
- `AnthropicVisionEngine`: agy's tests adapted (model default, timeout, workspace header sent when set and absent otherwise, error codes).
- Config: engine choice, defaults, invalid engine, timeout range, `CLAUDE_CODE_PATH` default lookup.
- Handler: agy's tests extended (label on new/duplicate/pending-phone parcels, order-only reply stores nothing, unsupported or oversized documents rejected without download, `not_configured` vs generic error replies, per-user sequential processing).

### Setup (user)

- `claude_code` (default): nothing beyond keeping Claude Code installed and logged in on this PC.
- `api` (backup): add credit in the Anthropic Console, set `VISION_ENGINE=api`, keep `ANTHROPIC_API_KEY`, and set `ANTHROPIC_MODEL=claude-haiku-4-5-20251001` or remove that line (it currently says `claude-3-5-haiku-20241022`).

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
2. Update `BUILD_PLAN.md` Part 2 (next version) and regenerate `SPEC.md`.
3. Commit on `build/v1`.
4. Restart the "VN Parcel Bot" task safely: stop the task, stop leftover bot processes and wait for them to exit, start the task, confirm "bot started" in the log.
5. Live check: Part C done; Part B by sending a real order screenshot in Telegram (engine `claude_code`); Part A at the next digest time.

## 7. Risks

| Risk | Mitigation |
|---|---|
| SPX blocks or changes the order-info endpoint | `blocked`/`http_status`/`parse` errors surface through the existing backoff and admin alerts; replies keep the spx.vn link; no evasion. |
| `retcode 2` also covers errors other than "unknown code" | An affected parcel stays pending and expires after 7 days, as before; the probe script shows the message. |
| SPX responses carry personal data | The parser reads only whitelisted fields; fixtures use placeholders; raw probe captures stay under the git-ignored `_raw` folder. |
| Claude Code is logged out, hits the Pro usage limit, or a CLI update changes its flags | `cli_error`/`not_configured` → generic or not-set-up reply, logged with codes only; the user can switch `VISION_ENGINE=api`. |
| Text inside a screenshot tries to steer the model | No tools, no MCP servers, prompt treats image text as data; output only feeds normal code detection and a 40-character label. |
| Vision misreads a code | The code still goes through normal detection and carrier lookups; wrong codes end as pending/expired or unknown replies. |
| API cost (backup engine only) | Haiku 4.5, one request per photo, `max_tokens` 1024. |

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
