<!-- Generated from BUILD_PLAN.md Part 2 (version 1.1). Do not edit by hand: edit BUILD_PLAN.md and regenerate. -->

# vn-parcel-bot — Specification

## 1. Overview

A personal Telegram bot, running on a Windows 10 PC in Vietnam, that watches parcels bought online and messages the owner of each parcel **every time a new tracking event appears**.

- Users are **buyers** receiving parcels. They add parcels by **pasting a tracking code** into a private chat with the bot. The bot works out the carrier itself (§4.3).
- **Tracked carriers** (polled, notified): SPX Express VN, J&T Express VN, Cainiao, 4PX, Ninja Van VN, GHN.
- **Link-only carriers** (recognised, answered with tracking links, never polled): BEST Express VN, YunExpress, GHTK, Viettel Post, VNPost/EMS, LEX VN.
- Used by the **admin (owner) plus a few allowlisted family/friends**. Each person sees and is notified only about their own parcels.
- The bot **polls the carriers' public tracking endpoints** directly (no paid aggregator) and uses Telegram **long polling** (no public URL, no webhook, no port forwarding).

## 2. Scope

In scope (v1):
- The twelve carriers and their tiers in §5.1; automatic carrier detection with auto-try (§4.3, §5.2).
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

All replies use `parse_mode=HTML`, link previews disabled. Every dynamic value inserted into a message is escaped with `html.escape`. Static strings in §17 are already HTML-safe (e.g. `J&amp;T`). URLs placed in `href` attributes are built only from the fixed templates in §5.1 plus the percent-encoded tracking code (§4.4).

### 4.1 Commands

| Command | Arguments | Behaviour |
|---|---|---|
| `/start` | – | `WELCOME` (with first name) followed by `HELP`. |
| `/help` | – | `HELP`. |
| `/track` | `<code> [last4] [carrier]` | Add a parcel (§4.3). The code may contain spaces/dashes (`/track SPXVN 0533 8454 932C`). A trailing carrier alias (§5.2, e.g. `ghn`, `4px`) forces that carrier and skips detection. A trailing 4-digit argument (before the alias, if any) is the phone override only when the forced carrier needs a phone or, without a forced carrier, the remaining code has a candidate that needs one; otherwise it stays part of the code. No args → `USAGE_TRACK`. |
| *(plain text)* | – | Routed per §4.2. |
| `/list` | – | Active parcels plus terminal parcels updated within `DELIVERED_VISIBLE_FOR` (3 days), numbered 1..n in `created_at` order. Unresolved parcels show `CARRIER_UNRESOLVED`. Empty → `LIST_EMPTY`. |
| `/status` | `<ref>` | Full history of one parcel, **newest first**, at most `MAX_EVENTS_IN_HISTORY` (30). `ref` = tracking code or the index shown by `/list`. |
| `/label` | `<ref> [name…]` | Set nickname (trimmed, max `MAX_LABEL_LENGTH` = 40 chars). No name → clear label. |
| `/remove` | `<ref>` | Delete the parcel and its events. |
| `/phone` | `[last4 \| clear]` | Default digits for carriers that need them (J&T, GHN). No arg → show saved default (or `PHONE_NONE`). 4 digits → save default. `clear` → remove default. Anything else → `INVALID_PHONE`. |
| `/check` | – | Immediately poll **this user's** active parcels, ignoring `next_check_at`. At most once per `CHECK_COOLDOWN` (5 min) per user (in-memory). Replies `CHECK_STARTED`, runs the cycle (updates arrive as normal notifications), then `CHECK_DONE`. |
| `/cancel` | – | Clear a pending phone question → `CANCELLED`; nothing pending → `NOTHING_TO_CANCEL`. |
| `/allow` *(admin)* | `<telegram_id> [name…]` | Upsert user with `is_allowed=1`; reply `ALLOWED`; try to DM `ALLOWED_NOTICE`. |
| `/revoke` *(admin)* | `<telegram_id>` | `is_allowed=0`; reply `REVOKED`. Admin id → `CANNOT_REVOKE_ADMIN`. |
| `/users` *(admin)* | – | All users with role and active parcel count. |
| `/health` *(admin)* | – | Last poll time and last `PollReport`, active parcel count, user count. |
| unknown `/command` | – | `UNKNOWN_COMMAND`. |

Commands advertised via `set_my_commands` (Vietnamese descriptions, §9.12): start, help, track, list, status, label, remove, phone, check, cancel. Admin commands are not advertised.

### 4.2 Plain-text routing

`route_text(text, has_pending)`:
1. If a phone question is pending **and** the stripped text is exactly 4 digits → `phone_for_pending`.
2. Else extract tracking codes from the text (`extract_codes`, §5.2). If ≥1 → `codes` (a pending question, if any, is discarded).
3. Else, if pending → reply `INVALID_PHONE` (keep pending). If not pending → `UNKNOWN_CODE`.

With `codes`:
- **One code** → same as `/track <code>`.
- **Several codes** → add each with no phone override and no forced carrier. `needs_phone` outcomes are not stored and are listed once in `NEEDS_PHONE_MULTI`; every other outcome gets its own reply. No pending question is created for multi-code messages.

### 4.3 Adding a parcel (`ParcelService.add`)

Inputs: the user, the raw code, an optional phone override, an optional forced carrier. A candidate counts as **tracked** only if it is tracked in §5.1 **and** present in the service's carrier mapping.

1. `code = normalize_code(raw)`. Candidates: forced carrier → `[forced]`, and `code` must match `GENERIC_CODE_RE` (§5.2) else `invalid_code`; otherwise `detect_carriers(code)`. No candidates → `invalid_code`.
2. Split candidates, preserving order, into `tracked` (tracked in §5.1 and present in the carrier mapping) and `link_only` (link-only in §5.1). Tracked carriers missing from the mapping are dropped. Both lists empty → `invalid_code`.
3. A phone override that fails `is_valid_last4` → `invalid_phone`.
4. `tracked` empty → `link_only` outcome with `link_carriers = link_only`. Nothing stored, no request.
5. The user already has a parcel with this tracking number (any carrier, any state) → `duplicate`. The user already has `max_parcels_per_user` (30) **active** parcels → `limit`.
6. `last4 = override or user.default_phone_last4`. `tryable` = tracked candidates that do not need a phone, plus those that do when `last4` is set. `phone_missing` = tracked candidates that need a phone while `last4` is `None`.
7. Fetch the `tryable` candidates **one by one in order**, stopping at the first result with `found=True`. A `CarrierError` is remembered and the next candidate is tried.
8. **Found** with carrier `c` → insert the parcel with `carrier=c`, `candidates=(c,)`, `phone_last4 = last4 if c needs a phone else None`, `next_check_at = now + poll_interval`; insert all events silently; set state (`delivered` / `returned` / `in_transit`); outcome `added` with the result. Reply `ADDED_FOUND` or `ADDED_DELIVERED`.
9. **Not found and `phone_missing` non-empty** → `needs_phone` with `candidates = phone_missing` (nothing stored). The handler stores `context.user_data["pending_phone"] = {"code": code, "carrier": forced}` and replies `ASK_PHONE`. The next 4-digit message calls `add` again with those digits (all tryable candidates are fetched again).
10. **Otherwise** insert a pending parcel: `candidates = tracked`; `carrier = tracked[0]` if there is exactly one tracked candidate, else `None` (unresolved); `phone_last4 = last4` if any tracked candidate needs a phone, else `None`; `next_check_at = now + poll_interval`.
    - Every attempted fetch raised `CarrierError` → record a failure with backoff (§6.4) and return `added` with `error` = the last error → `ADDED_ERROR`.
    - Else → `record_check_success(state="pending")` and return `added` with the last not-found result → `ADDED_PENDING` (resolved) or `ADDED_PENDING_AUTO` (unresolved).
    - Both pending replies append `ADDED_PENDING_PHONE_HINT` when any candidate needs a phone. `ADDED_ERROR` and both pending replies append `LINK_EXTRA` (§4.4) when `link_only` is non-empty (`link_carriers` on the outcome).

`DuplicateParcelError` from the repository (race) → `duplicate`. Different users may track the same code; each gets their own parcel row. The poller de-duplicates network requests (§6.2).

### 4.4 Link lists

`format_links(code, carriers)` returns one `LINK_ITEM` per carrier in `carriers` that has an official link template (§5.1), followed by one `LINK_ITEM` for 17TRACK, joined by `"\n"`.
- URL = template with `{code}` replaced by `urllib.parse.quote(code, safe="")`; templates without `{code}` are used as-is.
- The URL is inserted with `html.escape(url, quote=True)`; the name is the HTML-safe `CARRIER_NAMES` value or `LINK_17TRACK_NAME`.
- `LINK_ONLY` (outcome `link_only`) and `LINK_EXTRA` (pending replies) use `carrier_names(link_carriers)` and `format_links(code, link_carriers)`.

## 5. Carriers

### 5.1 Catalog

Facts probed from this PC on 2026-09-13 with fake codes unless marked otherwise.

| Code | Name | Tier | Needs phone | Evidence | Official link template |
|---|---|---|---|---|---|
| `spx` | SPX | tracked | no | JSON API answers without captcha; real-data signing unverified (§5.3) | – |
| `jt` | J&amp;T | tracked | yes | Server-rendered HTML (§5.4) | – |
| `cainiao` | Cainiao | tracked | no | JSON API, HTTP 200, no captcha (§5.5) | – |
| `fourpx` | 4PX | tracked | no | JSON API, HTTP 200, no captcha (§5.6) | – |
| `ninjavan` | Ninja Van | tracked | no | JSON API, 404 JSON for unknown codes (§5.7) | – |
| `ghn` | GHN | tracked | yes | JSON API with `phone_verify` hash (§5.8) | – |
| `best` | BEST Express | link-only | – | Old API path now serves the new site's HTML; site ships a rotate-captcha service. Promote after Prompt 10A only if an open endpoint is found (Appendix B) | `https://www.best-inc.vn/track?bills={code}` |
| `yunexpress` | YunExpress | link-only | – | `services.yuntrack.com` returns an Alibaba Cloud firewall page (HTTP 405) | `https://www.yuntrack.com/parcelTracking?id={code}` |
| `ghtk` | GHTK | link-only | – | Tracking page requires Google reCAPTCHA (`invalid_captcha` error code in its script) | `https://i.ghtk.vn/{code}` |
| `viettelpost` | Viettel Post | link-only | – | JavaScript cookie challenge (`document.cookie=…; location.reload`) | `https://viettelpost.com.vn/tra-cuu-hanh-trinh-don/` |
| `vnpost` | VNPost | link-only | – | Tracking tab renders a captcha (`tracuu.js`) | `https://vnpost.vn/vi/ca-nhan/chuyen-phat/chuyen-phat-trong-nuoc#!?tab=tra-cuu-hanh-trinh&code={code}` |
| `lex` | LEX VN | link-only | – | `tracker.lel.asia` no longer resolves; logistics site loads Lazada anti-bot script | `https://logistics.lazada.vn/` |

Every link list ends with 17TRACK: `https://t.17track.net/vi#nums={code}`.

Link-only carriers are never polled and never stored. The bot does **not** solve captchas, replay cookie challenges, drive headless browsers, or rotate User-Agents.

### 5.2 Code normalization, detection and aliases

- `normalize_code(raw)`: uppercase; remove all whitespace and `-`; strip surrounding `,;:()[]<>"'.`. Internal dots are kept (GHTK codes contain them).
- `GENERIC_CODE_RE = ^[0-9A-Z][0-9A-Z.]{4,38}[0-9A-Z]$` — the minimum shape of any code, used for forced carriers.
- `detect_carriers(code)` on a normalized code — the **first** matching rule wins and returns its candidates in order:

| # | Regex | Candidates | Source |
|---|---|---|---|
| 1 | `^SPXVN[0-9A-Z]{8,16}$` | spx | observed |
| 2 | `^SPEVN[0-9A-Z]{6,20}$` | ninjavan | web (Ninja Van codes on Shopee) |
| 3 | `^LP\d{14}$` | cainiao | open-source trackers |
| 4 | `^[A-Z]{2}\d{9}CN$` | cainiao | UPU S10 (China Post / AliExpress) |
| 5 | `^4PX[0-9A-Z]{10,20}$` | fourpx | open-source tracker |
| 6 | `^YT\d{16}$` | yunexpress | web |
| 7 | `^[A-Z]{2}\d{9}VN$` | vnpost | UPU S10 |
| 8 | `^(LEXVN\|LXVN\|LVS)[0-9A-Z]{6,20}$` | lex | web, unverified |
| 9 | `^S\d{5,10}(\.[0-9A-Z]{1,12}){1,4}$` | ghtk | web |
| 10 | `^\d{12}$` | jt, best, viettelpost | observed (J&T); web |
| 11 | `^\d{13}$` | best | web |
| 12 | `^(?=[0-9A-Z]*[A-Z])(?=[0-9A-Z]*\d)[0-9A-Z]{8,14}$` | ghn, ninjavan | web; unprefixed alphanumeric codes |

  No rule matches → `[]`.
- `extract_codes(text)`: iterate `re.finditer(r"[0-9A-Za-z][0-9A-Za-z.\-]*[0-9A-Za-z]", text)`; normalize each token; keep tokens with a non-empty `detect_carriers`. A token that only matches **rule 12** is kept only when the whole stripped message is that single token. Return in order of appearance, de-duplicated. No joining of space-separated fragments.
- `is_valid_last4(s)`: `^\d{4}$`.
- `parse_carrier_alias(text)`: casefold and remove spaces, `-`, `_`, `.`, `&`, then map:
  `spx`, `shopee`, `shopeeexpress` → spx · `jt`, `jnt`, `jtexpress` → jt · `cainiao` → cainiao · `4px`, `fourpx` → fourpx · `ninjavan`, `ninja`, `nv` → ninjavan · `ghn`, `giaohangnhanh` → ghn · `best`, `bestexpress` → best · `yun`, `yunexpress`, `yuntrack` → yunexpress · `ghtk`, `giaohangtietkiem` → ghtk · `viettelpost`, `viettel`, `vtp` → viettelpost · `vnpost`, `vnp`, `ems` → vnpost · `lex`, `lazada`, `lel` → lex · anything else → `None`.
- `mask_code(code)`: `code[:5] + "…" + code[-3:]`, used in logs.

Prompt 10A updates this section and `tracking_codes.py` together when real codes contradict a rule.

### 5.3 SPX Express Vietnam

| Item | Value | Confidence |
|---|---|---|
| Endpoint | `GET https://spx.vn/api/v2/fleet_order/tracking/search?sls_tracking_number=<VALUE>` | Verified (HTTP 200) |
| Unknown code | `{"retcode": 0, "message": "", "data": {}}` | Verified |
| Found response | `data.sls_tracking_number`, `data.current_status` (display text), `data.tracking_list[]` items with `message` (text), `timestamp` (Unix seconds), `code`; also `data.status_list[]` | Field names verified in spx.vn's own page script (2026-09-13); values unverified |
| Request signing | The SPX Thailand client sends `VALUE = f"{code}\|{ts}{sha256(code + ts + SECRET)}"` (`ts` = Unix seconds as a string, `SECRET` per country). No Vietnamese `SECRET` was found in spx.vn's public scripts. | **Unverified** — decided in Prompt 10A |
| Delivered / returned | Markers in `current_status` or the latest `message` (§9.7) | Unverified |

- `SPX_SIGNING_SECRET: str | None = None`. `None` → `VALUE = code`. A string → the signed form. Prompt 10A sets it only if real codes need it and records where the value came from.
- Parsing: `retcode != 0` → `parse` error. `data` empty or `tracking_list` missing/empty → not found. `tracking_list` not a list, or an item without an integer `timestamp` or a string `message` → `parse` error.
- Event: `time = datetime.fromtimestamp(timestamp, UTC)`; `description` = `message` with literal `\n` sequences replaced by a space, whitespace-collapsed; `raw_status = str(code)` when present; `location = None`.
- `delivered` = any `DELIVERED_MARKERS` (casefold substring) in `current_status` or the latest description. `returned` = not delivered and any `RETURNED_MARKERS` in `current_status` or the latest description.

Tracking code format: `SPXVN` + 8–16 uppercase alphanumerics (observed examples have 11–14, e.g. `SPXVN05338454932C`).

### 5.4 J&T Express Vietnam

| Item | Value | Confidence |
|---|---|---|
| Tracking page | `https://jtexpress.vn/vi/tracking` | Verified |
| Lookup | Server-rendered HTML. The page's form is `GET https://jtexpress.vn/tracking` with `type=track` and `billcode=<CODE>`; phone digits parameter believed to be `cellphone=<LAST4>` | Form verified; **how the phone digits are actually submitted is unverified** (the hidden `cellphone` input is commented out in the HTML and a separate `tracking_cellphone.js` + verify modal exist) |
| Not-found marker | Text `Không tìm thấy dữ liệu về vận đơn` and/or an `.empty-vandon` block | Verified for a fake code |
| Result markup | Believed to be inside `.result-tracking` | Unverified for real data — confirmed by Prompt 10A |
| Captcha / CSRF / signature on GET | None observed | Verified for fake code |
| Requires last 4 digits of recipient phone | Yes (page asks for it) | Verified via public sources |

Tracking code format: exactly 12 digits (e.g. `841000072647`).

### 5.5 Cainiao

| Item | Value | Confidence |
|---|---|---|
| Endpoint | `GET https://global.cainiao.com/global/detail.json?mailNos=<CODE>&lang=en-US&language=en-US` | Verified (HTTP 200 JSON, no captcha, no special headers) |
| Unknown code | `{"module":[{"mailNo":"<CODE>","mailNoSource":"EXTERNAL","detailList":[]}],"success":true}` | Verified |
| Found response | `module[0]` with `status`, `statusDesc`, `originCountry`, `destCountry`, `detailList[]` items with `time` (epoch ms), `timeStr` (`yyyy-MM-dd HH:mm:ss`), `timeZone` (e.g. `GMT+8`), `desc`, `standerdDesc`, `descTitle`, `actionCode` | Open-source schema (shlee322/delivery-tracker) |
| Delivered | Latest `actionCode == "GTMS_SIGNED"` | Open-source |
| Returned | Latest `actionCode` contains `RETURN` | Unverified |

- Parsing: `success` is not `True`, or `module` is not a non-empty list → `parse` error. `detailList` missing or empty → not found. An item without a usable time or without `desc`/`standerdDesc` → `parse` error.
- Event time: integer `time` → `datetime.fromtimestamp(time / 1000, UTC)`; else `timeStr` parsed as `%Y-%m-%d %H:%M:%S` in the offset from `timeZone` (default UTC+8). `description = desc` (fallback `standerdDesc`); `raw_status = actionCode`; `location = None`.

### 5.6 4PX

| Item | Value | Confidence |
|---|---|---|
| Endpoint | `POST https://track.4px.com/track/v2/front/listTrackV3`, JSON body `{"queryCodes": ["<CODE>"], "language": "en-us", "translateLanguage": "en-us"}` | Verified (HTTP 200 JSON, no captcha) |
| Unknown code | `{"result":1,"message":"操作成功","data":[{"queryCode":"<CODE>","status":7,"tracks":null,…}],"tag":"7"}` | Verified |
| Found response | `data[0].tracks[]` items with `tkCode`, `tkDesc`, `tkLocation`, `tkTimezone`, `tkDate`, `tkDateStr` (`yyyy-MM-dd HH:mm:ss`), `tkTranslatedDesc` | Open-source (itsvic-dev/deliveries) |
| Delivered | Latest `tkCode` starts with `FPX_S_OK` | Open-source |
| Returned | None known | – |

- Parsing: `result != 1` → `parse` error. `data` empty, or `tracks` null/empty → not found. An item without `tkDateStr` or without `tkDesc`/`tkTranslatedDesc` → `parse` error.
- Event time: `tkDateStr` in the offset parsed from `tkTimezone` (accepts `+08:00`, `GMT+8`, `UTC+8`, `8`); missing or unparseable → UTC+8. `description = tkDesc` (fallback `tkTranslatedDesc`); `location = tkLocation` or `None`; `raw_status = tkCode`.

### 5.7 Ninja Van Vietnam

| Item | Value | Confidence |
|---|---|---|
| Endpoint | `GET https://api.ninjavan.co/vn/dash/1.2/public/orders?tracking_id=<CODE>` | Verified |
| Unknown code | HTTP 404 `{"error":{"code":150002,"title":"Not Found","message":"order by tracking id <CODE> not found."}}` | Verified |
| Found response | Top-level object with `events[]` (items: `type`, `time`, `data` with `hubName` and `failureReason.{en,vi}`) and a granular status | Names from ninjavan.co's page script, which camel-cases the raw JSON; raw casing unverified |
| Delivered | Latest event `type` in `DELIVERY_SUCCESS`, `FORCED_SUCCESS`, `FROM_DP_TO_CUSTOMER` and not returned | Page script |
| Returned | Granular status equals `returned to sender` (casefold) | Page script |

- The API returns event **types**, not texts. `NINJAVAN_EVENT_TEXT` (§9.7) maps types to Vietnamese; an unknown type becomes `type.replace("_", " ").capitalize()`.
- Accept snake_case and camelCase keys everywhere (`hub_name`/`hubName`, `failure_reason`/`failureReason`, `granular_status`/`granularStatus`).
- Event: `time` as an ISO-8601 string (`Z` or offset) or epoch milliseconds; `description` = mapped text, plus ` – <reason>` for `DELIVERY_FAILURE` when `failureReason.vi` or `.en` exists; `location` = hub name or `None`; `raw_status = type`.
- A body without a top-level `events` key whose `data` is an object is unwrapped to `data` first.
- HTTP 404 with `error.code == 150002` → not found; any other 404 → `http_status`. A 200 body without an `events` list → `parse` error; an empty `events` list → not found.

### 5.8 GHN

| Item | Value | Confidence |
|---|---|---|
| Endpoint | `POST https://fe-online-gateway.ghn.vn/order-tracking/public-api/client/tracking-logs`, JSON `{"order_code": "<CODE>", "phone_verify": "<HASH>"}` | Verified |
| Phone hash | `HASH = sha256(f"{CODE}\|{LAST4}".encode("utf-8")).hexdigest()` — the site keeps a 4-digit input as-is before hashing | Verified in the site script |
| Missing / wrong digits | HTTP 400 `{"code":400,"message":"phone verify param is missing","data":null,"code_message":"PHONE_VERIFY_REQUIRED"}`; wrong digits → `code_message` `PHONE_VERIFY_FAIL` | REQUIRED verified; FAIL from script |
| Found response | `{"code":200,"data":{"order_info":{"status":…},"tracking_logs":[{"status","status_name","action_at","location":{…}}]}}` | Field names from the site script |
| Delivered | `order_info.status == "delivered"` or latest log `status == "delivered"` | Script |
| Returned | `order_info.status == "returned"` or latest log `status == "returned"` | Script |

- HTTP 400 does not raise by itself: GHN reads the JSON body first. Body `code == 200` → parse `data`; `tracking_logs` missing/empty → not found. Body `code == 400` (any `code_message`, including wrong digits and unknown orders) → not found. Any other body code, or a non-JSON 400 → `http_status`.
- Event: `time = datetime.fromisoformat(action_at)` (`Z` accepted; naive → Asia/Ho_Chi_Minh); `description = status_name` or `GHN_STATUS_TEXT[status]` or `status`; `location = location["address"]` when it is a string, else `None`; `raw_status = status`.
- `GHN_STATUS_TEXT` (from the site script): `draft` Đơn nháp · `cancel` Đã hủy · `ready_to_pick` Chờ lấy hàng · `picking` Đang lấy hàng · `money_collect_picking` Đang thu tiền người gửi · `picked` Đã lấy hàng · `storing` Lưu kho · `transporting` Đang luân chuyển hàng · `sorting` Đang phân loại hàng · `delivering` Đang giao hàng · `money_collect_delivering` Đang thu tiền người nhận · `delivery_fail` Giao hàng thất bại · `delivered` Giao hàng thành công · `waiting_to_return` Chờ trả hàng · `return` Trả hàng · `return_transporting` Đang luân chuyển hàng trả · `return_sorting` Đang phân loại hàng trả · `returning` Đang trả hàng · `return_fail` Trả hàng thất bại · `returned` Trả hàng thành công · `exception` Đơn ngoại lệ · `lost` Hàng thất lạc · `damage` Hàng hư hỏng.

### 5.9 Fetch contract (all tracked carriers)

- One shared `httpx.AsyncClient` from `make_http_client(settings)`: timeout `HTTP_TIMEOUT_SECONDS`, `follow_redirects=True`, static headers `DEFAULT_HEADERS` (a normal desktop Chrome `User-Agent`, `Accept-Language: vi-VN,vi;q=0.9,en;q=0.8`). **No User-Agent rotation, no evasion techniques.** Carrier traffic never goes through `TELEGRAM_PROXY_URL` (carriers need the Vietnamese home IP).
- All requests go through `carriers/common.py` `request()` (§9.7). Error mapping → `CarrierError(carrier, reason, detail)`:
  - `httpx.TimeoutException`, `httpx.TransportError` → `network`
  - HTTP 403 or 429, or a captcha / JS-challenge page → `blocked`
  - any other non-2xx status, unless the carrier section defines it as not-found (Ninja Van 404/150002, GHN 400) → `http_status`
  - unparseable body, unexpected structure → `parse`; a 200 response that should be JSON but is HTML → `blocked`
- "Not found" is **not** an error: return `TrackingResult(found=False)`.
- `found=True` requires at least one event; an empty event list is reported as not found.
- Carriers that need a phone raise `ValueError` when `phone_last4` is `None` (a programming error, never a user error).
- Event times must become timezone-aware datetimes (carrier-local times use the offsets in each section; unspecified local times are Asia/Ho_Chi_Minh).
- Events are returned **ascending by time** (stable for equal timestamps).
- `delivered` / `returned` flags come from the marker constants in each carrier module.

### 5.10 Politeness

- Poll interval default 20 min, minimum 5 min.
- Requests to the same carrier are sequential with `REQUEST_DELAY_SECONDS` (3 s) + random 0–`JITTER_SECONDS` (2 s) between them. Different carriers are polled concurrently.
- Identical `(carrier, code, last4)` fetch keys across parcels and users → one request per cycle.
- An unresolved parcel costs one request per tryable candidate per cycle (at most two with the rules in §5.2).
- Terminal parcels are never polled. Link-only carriers are never requested.
- When adding a parcel (§4.3) candidates are fetched one after another without the delay (at most two requests, triggered by the user).

## 6. Polling and notifications

### 6.1 Schedule

- Job `poll` runs every `POLL_INTERVAL_MINUTES`, first run 30 s after start (this is the catch-up after the PC was off or asleep).
- `Poller.run_cycle` is guarded by an `asyncio.Lock`. Scheduled job: if locked, return `PollReport(skipped=True)` immediately. `/check`: `wait=True` (queues behind the running cycle).

### 6.2 Cycle algorithm

```
now = clock()
parcels = repo.due_parcels(now)                    # active, owner allowed, next_check_at <= now
          or repo.active_parcels_for_user(uid)     # when only_user_id is given
fetch_keys(parcel) = [FetchKey(c, parcel.tracking_number, parcel.phone_last4 if needs_phone(c) else None)
                      for c in parcel.try_order()  # (carrier,) when resolved, else candidates
                      if c in carriers and (not needs_phone(c) or parcel.phone_last4)]

# fetch phase
keys = unique fetch keys of all parcels, in first-appearance order, grouped by carrier
for each carrier concurrently:
    for i, key in enumerate(keys of this carrier):
        if i > 0: await sleep(REQUEST_DELAY_SECONDS + rand() * JITTER_SECONDS)
        try: outcomes[key] = await carrier.fetch(http, key.tracking_number, key.phone_last4)
        except CarrierError as err: outcomes[key] = err; failures[carrier] += 1

# process phase, parcels in order (each parcel is re-read first and skipped if it was
# deleted or is no longer active since the cycle started)
for parcel in parcels:
    keys = fetch_keys(parcel)
    if not keys: continue
    if parcel.is_resolved:
        outcome = outcomes[keys[0]]
        CarrierError → handle_failure(parcel, outcome) else handle_result(parcel, outcome)
    else:
        found = first key (candidate order) whose outcome is a found result
        if found: repo.resolve_carrier(parcel.id, found.carrier); handle_result(refreshed parcel, result, resolved_now=True)
        elif any outcome is a CarrierError: handle_failure(parcel, first error)   # back off while a candidate fails
        else: handle_result(parcel, the first not-found result)

after all parcels: stale check, carrier alerts, purge, save meta "last_poll_report"
```

### 6.3 Handling a result for one parcel

1. **found**
   - `new = repo.insert_events(parcel.id, result.events)` (only events whose key is new).
   - `state = delivered if result.delivered else returned if result.returned else in_transit`.
   - `repo.record_check_success(...)`: `last_status_text` = latest event description, `last_event_at` = latest event time, `consecutive_failures=0`, `next_check_at = now + interval`, `delivered_at` = latest event time when newly delivered.
   - If `new` is non-empty, or the state became `delivered`/`returned` in this cycle → send **one message per parcel** built by `format_event_update(parcel, new, tz, delivered=…, returned=…, resolved_carrier=…)`; the delivered/returned footer is included only when the state changes in this cycle; `UPDATE_RESOLVED` is included only when the carrier was resolved in this cycle.
2. **not found**
   - A resolved parcel that already has stored events → treat as `CarrierError(carrier, "parse", "events disappeared")` (§6.4). Never delete events.
   - Else if `now - created_at > PENDING_EXPIRY` (7 days) → state `expired`, send `EXPIRED`.
   - Else → `record_check_success(state="pending", …)`; no message.
3. **Stale** — after processing, any `in_transit` parcel in this cycle with `last_event_at < now - STALE_AFTER` (30 days) → state `stale`, send `STALE`.

### 6.4 Failures and backoff

- `n = repo.record_check_failure(parcel.id, next_check_at=…, now=now)` where `next_check_at = now + min(interval × 2ⁿ, MAX_BACKOFF)` using the **new** failure count `n` (`MAX_BACKOFF` = 6 h).
- A `pending` parcel created more than `PENDING_EXPIRY` ago whose check fails is expired (state `expired`, `EXPIRED` sent) instead of being backed off, so a failing carrier cannot keep it alive.
- `PollReport.failures[carrier]` counts failed **fetches** per carrier (fetch phase).
- **Carrier alert** to the admin (`ALERT_CARRIER`) when, in one cycle, a parcel reaches exactly `FAILURE_ALERT_THRESHOLD` (5) consecutive failures (alert for the carrier of the error that caused it), **or** every fetch for a carrier failed and there were ≥ `CARRIER_ALL_FAILED_MIN_FETCHES` (3) fetches. At most one alert per carrier per `ALERT_COOLDOWN` (6 h), stored in meta key `alert:<carrier>` (ISO time).
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
  carrier TEXT CHECK (carrier IS NULL OR carrier IN ('spx', 'jt', 'cainiao', 'fourpx', 'ninjavan', 'ghn',
                                                    'best', 'yunexpress', 'ghtk', 'viettelpost', 'vnpost', 'lex')),
  candidates TEXT NOT NULL CHECK (length(candidates) > 0),
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
  CHECK (carrier IS NOT NULL OR state IN ('pending', 'expired')),
  UNIQUE (user_id, tracking_number)
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

- `carrier IS NULL` means **unresolved**: the parcel has several candidates and none has returned data yet. Unresolved parcels can only be `pending` or `expired`.
- `candidates` stores tracked carrier codes in try order, comma-separated (`ghn,ninjavan`). A resolved parcel stores exactly its carrier.
- The `carrier` CHECK lists all twelve codes so that promoting a link-only carrier needs no migration.
- `parcels.phone_last4` stores the digits **actually used** for the parcel (override or the user's default at add time), so later changes to the default do not affect existing parcels. It is `NULL` when no candidate needs a phone.

**Event key**: first 16 hex chars of SHA-1 over `"{utc_iso_seconds}|{norm(description)}|{norm(location or '')}"`, where `norm` = collapse whitespace, strip, `casefold()`.

## 8. Architecture

```
Telegram ⇄ python-telegram-bot (long polling, JobQueue)
              │
     bot/ (handlers, auth gate, notifier)            ← thin: parse input, call services, send text
              │
     services/ (ParcelService, Poller, formatting)    ← all business rules, unit-tested with fakes
              │                     │
     db/ Repository (aiosqlite)   carriers/ (SPX, J&T, Cainiao, 4PX, Ninja Van, GHN) ⇄ httpx ⇄ carrier sites
              │
     carrier_catalog.py + tracking_codes.py (pure: tiers, links, aliases, detection)
```

### 8.1 Repository layout

```
vn-parcel-bot/
├─ BUILD_PLAN.md                spec + build prompts (this document)
├─ SPEC.md                      generated copy of Part 2
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
│  ├─ carrier_catalog.py        CarrierCode, CarrierInfo, CATALOG, links, aliases
│  ├─ tracking_codes.py         normalize/detect/extract codes
│  ├─ carriers/
│  │  ├─ __init__.py            CARRIERS registry, get_carrier
│  │  ├─ models.py              TrackingEvent, TrackingResult, CarrierError, Carrier protocol
│  │  ├─ http.py                DEFAULT_HEADERS, make_http_client
│  │  ├─ common.py              request, json_body, looks_like_challenge, parse_gmt_offset, clean_text
│  │  ├─ spx.py                 parse_spx_response, sign_spx_code, SpxCarrier
│  │  ├─ jt.py                  parse_jt_html, JtCarrier
│  │  ├─ cainiao.py             parse_cainiao_response, CainiaoCarrier
│  │  ├─ fourpx.py              parse_fourpx_response, FourPxCarrier
│  │  ├─ ninjavan.py            parse_ninjavan_response, NinjaVanCarrier
│  │  └─ ghn.py                 parse_ghn_response, ghn_phone_verify, GhnCarrier
│  ├─ db/
│  │  ├─ __init__.py
│  │  ├─ schema.py              SCHEMA_VERSION, MIGRATIONS, migrate
│  │  └─ repo.py                User, Parcel, Repository, DuplicateParcelError
│  ├─ services/
│  │  ├─ __init__.py
│  │  ├─ formatting.py          pure message builders
│  │  ├─ parcels.py             AddOutcome, ParcelService
│  │  └─ poller.py              Notifier protocol, FetchKey, PollReport, Poller
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
│  ├─ uninstall-task.ps1
│  └─ status-bot.ps1
├─ tests/
│  ├─ conftest.py
│  ├─ fakes.py                  FakeCarrier, FakeNotifier, FakeClock, ev
│  ├─ fixtures/
│  │  ├─ FIXTURES.md            provenance and observed request/response facts
│  │  ├─ spx/ jt/ cainiao/ fourpx/ ninjavan/ ghn/   in_transit, delivered, not_found [, returned]
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
    poll_interval_minutes: int = 20  # 5..240
    request_delay_seconds: float = 3.0  # 0..60
    http_timeout_seconds: float = 15.0  # >0..120
    db_path: Path = Path("data/bot.sqlite3")
    log_dir: Path = Path("logs")
    log_level: str = "INFO"  # DEBUG|INFO|WARNING|ERROR
    timezone: str = "Asia/Ho_Chi_Minh"
    quiet_hours: tuple[int, int] | None = (22, 7)
    max_parcels_per_user: int = 30  # 1..200
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
    def filter(
        self, record: logging.LogRecord
    ) -> bool: ...  # replaces secret in msg/args with "***"


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
    def __enter__(
        self,
    ) -> (
        "SingleInstanceLock"
    ): ...  # creates parent dir; msvcrt.locking(LK_NBLCK, 1) → SingleInstanceError if held
    def __exit__(self, *exc) -> None: ...  # unlock + close
```

### 9.5 `carrier_catalog.py` and `tracking_codes.py` (pure, no I/O)

```python
# carrier_catalog.py
CarrierCode = Literal[
    "spx",
    "jt",
    "cainiao",
    "fourpx",
    "ninjavan",
    "ghn",
    "best",
    "yunexpress",
    "ghtk",
    "viettelpost",
    "vnpost",
    "lex",
]


@dataclass(frozen=True)
class CarrierInfo:
    code: CarrierCode
    display_name: str  # plain text: "SPX", "J&T", "LEX VN"
    tracked: bool
    needs_phone: bool
    link_template: str | None  # §5.1; "{code}" placeholder; None for tracked carriers


CATALOG: dict[CarrierCode, CarrierInfo]  # insertion order = §5.1 table order
TRACKED: tuple[CarrierCode, ...]  # ("spx", "jt", "cainiao", "fourpx", "ninjavan", "ghn")
SEVENTEEN_TRACK_TEMPLATE = "https://t.17track.net/vi#nums={code}"


def is_tracked(carrier: CarrierCode) -> bool: ...
def needs_phone(carrier: CarrierCode) -> bool: ...
def official_url(carrier: CarrierCode, code: str) -> str | None: ...
def seventeen_track_url(code: str) -> str: ...
def parse_carrier_alias(text: str) -> CarrierCode | None: ...


# tracking_codes.py
GENERIC_CODE_RE: re.Pattern[str]


def normalize_code(raw: str) -> str: ...
def detect_carriers(code: str) -> list[CarrierCode]: ...
def extract_codes(text: str) -> list[str]: ...
def is_valid_last4(value: str) -> bool: ...
def mask_code(code: str) -> str: ...  # code[:5] + "…" + code[-3:]
```

### 9.6 `carriers/models.py`

```python
ErrorReason = Literal["network", "blocked", "http_status", "parse"]


@dataclass(frozen=True)
class TrackingEvent:
    time: datetime  # must be timezone-aware, else ValueError
    description: str
    location: str | None = None
    raw_status: str | None = None

    @property
    def key(self) -> str: ...  # §7 event key


@dataclass(frozen=True)
class TrackingResult:
    carrier: CarrierCode
    tracking_number: str
    found: bool
    events: tuple[TrackingEvent, ...] = ()  # __post_init__ stores a stable sort ascending by time
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
    display_name: str  # "SPX" / "J&T" (plain text; formatting escapes)
    needs_phone: bool

    async def fetch(
        self, http: httpx.AsyncClient, tracking_number: str, phone_last4: str | None = None
    ) -> TrackingResult: ...
```

### 9.7 `carriers/`

```python
# http.py
DEFAULT_HEADERS: dict[str, str]
def make_http_client(settings: Settings) -> httpx.AsyncClient: ...

# common.py
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
async def request(http: httpx.AsyncClient, carrier: CarrierCode, method: str, url: str, *,
                  not_found_statuses: Collection[int] = (), **kwargs) -> httpx.Response: ...
    # network errors → "network"; 403/429 → "blocked"; other non-2xx not in not_found_statuses → "http_status";
    # a 2xx text body that looks_like_challenge → "blocked"
def json_body(carrier: CarrierCode, response: httpx.Response) -> Any: ...
    # invalid JSON → "blocked" if the body starts with "<", else "parse"
def looks_like_challenge(text: str) -> bool: ...
    # casefold contains "captcha", "cf-challenge", "x5sec" or "punish", or both "document.cookie" and "location.reload"
def parse_gmt_offset(value: object, default: tzinfo) -> tzinfo: ...
    # "GMT+8", "UTC-3", "+08:00", "+0530", "8", 8 → fixed offset; None/unparseable → default
def clean_text(value: object) -> str: ...   # " ".join(str(value).split())

# spx.py
SPX_TRACKING_URL = "https://spx.vn/api/v2/fleet_order/tracking/search"
SPX_SIGNING_SECRET: str | None = None
DELIVERED_MARKERS = ("delivered", "giao hàng thành công", "giao thành công")
RETURNED_MARKERS = ("returned", "hoàn hàng thành công", "đã hoàn hàng", "trả hàng thành công")
def sign_spx_code(code: str, timestamp: int, secret: str) -> str: ...
    # f"{code}|{timestamp}{sha256(f'{code}{timestamp}{secret}'.encode()).hexdigest()}"
def parse_spx_response(payload: object, tracking_number: str) -> TrackingResult: ...
class SpxCarrier:  code = "spx"; display_name = "SPX"; needs_phone = False
    def __init__(self, *, secret: str | None = SPX_SIGNING_SECRET,
                 clock: Callable[[], float] = time.time) -> None: ...

# jt.py
JT_TRACKING_URL = "https://jtexpress.vn/tracking"      # adjust only if Prompt 10A proves otherwise
NOT_FOUND_MARKER = "Không tìm thấy dữ liệu"
DELIVERED_MARKERS: tuple[str, ...]
RETURNED_MARKERS: tuple[str, ...]
def parse_jt_html(html: str, tracking_number: str) -> TrackingResult: ...
class JtCarrier:   code = "jt"; display_name = "J&T"; needs_phone = True

# cainiao.py
CAINIAO_TRACKING_URL = "https://global.cainiao.com/global/detail.json"
DELIVERED_ACTION_CODES = ("GTMS_SIGNED",)
def parse_cainiao_response(payload: object, tracking_number: str) -> TrackingResult: ...
class CainiaoCarrier: code = "cainiao"; display_name = "Cainiao"; needs_phone = False

# fourpx.py
FOURPX_TRACKING_URL = "https://track.4px.com/track/v2/front/listTrackV3"
DELIVERED_CODE_PREFIX = "FPX_S_OK"
def parse_fourpx_response(payload: object, tracking_number: str) -> TrackingResult: ...
class FourPxCarrier: code = "fourpx"; display_name = "4PX"; needs_phone = False

# ninjavan.py
NINJAVAN_TRACKING_URL = "https://api.ninjavan.co/vn/dash/1.2/public/orders"
NOT_FOUND_ERROR_CODE = 150002
DELIVERED_TYPES = ("DELIVERY_SUCCESS", "FORCED_SUCCESS", "FROM_DP_TO_CUSTOMER")
RETURNED_GRANULAR_STATUS = "returned to sender"
NINJAVAN_EVENT_TEXT: dict[str, str]
def parse_ninjavan_response(payload: object, tracking_number: str) -> TrackingResult: ...
class NinjaVanCarrier: code = "ninjavan"; display_name = "Ninja Van"; needs_phone = False

# ghn.py
GHN_TRACKING_URL = "https://fe-online-gateway.ghn.vn/order-tracking/public-api/client/tracking-logs"
GHN_STATUS_TEXT: dict[str, str]                        # §5.8
def ghn_phone_verify(code: str, last4: str) -> str: ...
def parse_ghn_response(payload: object, tracking_number: str) -> TrackingResult: ...
class GhnCarrier: code = "ghn"; display_name = "GHN"; needs_phone = True

# __init__.py
CARRIERS: dict[CarrierCode, Carrier]   # exactly the TRACKED codes, in TRACKED order
def get_carrier(code: CarrierCode) -> Carrier: ...
```

`NINJAVAN_EVENT_TEXT`:

| Type | Text |
|---|---|
| `ADDED_TO_SHIPMENT` | Đã thêm vào chuyến hàng |
| `ARRIVED_AT_ORIGIN_HUB` | Đã đến kho gửi |
| `ARRIVED_AT_TRANSIT_HUB` | Đã đến kho trung chuyển |
| `ARRIVED_AT_DESTINATION_HUB` | Đã đến kho giao |
| `HUB_INBOUND_SCAN` | Đã nhập kho |
| `FIRST_HUB_INBOUND_SCAN` | Đã nhập kho đầu tiên |
| `PARCEL_ROUTING_SCAN` | Đang phân tuyến |
| `ROUTE_INBOUND_SCAN` | Đã nhận vào tuyến giao |
| `DRIVER_PICKUP_SCAN` | Tài xế đã lấy hàng |
| `DRIVER_INBOUND_SCAN` | Tài xế đang đi giao hàng |
| `DELIVERY_FAILURE` | Giao hàng thất bại |
| `DELIVERY_SUCCESS` | Giao hàng thành công |
| `FORCED_SUCCESS` | Giao hàng thành công |
| `FROM_SHIPPER_TO_DP` | Người gửi đã gửi hàng tại điểm nhận |
| `FROM_DRIVER_TO_DP` | Hàng đã đến điểm nhận |
| `FROM_DP_TO_DRIVER` | Điểm nhận đã giao hàng cho tài xế |
| `FROM_DP_TO_CUSTOMER` | Đã nhận hàng tại điểm nhận |
| `CANCEL` | Đơn đã bị hủy |
| `RESCHEDULE` | Đã hẹn lại lịch giao |
| `RESUME` | Tiếp tục xử lý đơn |
| `RTS` | Đang hoàn hàng về người gửi |

### 9.8 `db/schema.py`, `db/repo.py`

```python
# schema.py
SCHEMA_VERSION = 1
MIGRATIONS: list[str]  # index i = SQL script bringing version i → i+1


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
    carrier: CarrierCode | None  # None = unresolved
    candidates: tuple[CarrierCode, ...]  # try order; (carrier,) when resolved
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
    @property
    def is_resolved(self) -> bool: ...
    def try_order(self) -> tuple[CarrierCode, ...]: ...  # (carrier,) when resolved, else candidates


class Repository:
    @classmethod
    async def open(
        cls, db_path: Path | str
    ) -> "Repository": ...  # creates parent dir, pragmas, migrate
    async def close(self) -> None: ...
    # users
    async def upsert_user(
        self,
        telegram_id: int,
        *,
        now: datetime,
        name: str | None = None,
        is_allowed: bool | None = None,
        is_admin: bool | None = None,
    ) -> User: ...
    async def get_user(self, telegram_id: int) -> User | None: ...
    async def list_users(self) -> list[User]: ...
    async def set_default_phone(self, telegram_id: int, last4: str | None) -> None: ...
    # parcels
    async def add_parcel(
        self,
        *,
        user_id: int,
        carrier: CarrierCode | None,
        candidates: Sequence[CarrierCode],
        tracking_number: str,
        phone_last4: str | None,
        now: datetime,
        next_check_at: datetime,
    ) -> Parcel:
        ...
        # ValueError if candidates is empty, or carrier is not None and tuple(candidates) != (carrier,)

    async def get_parcel(self, parcel_id: int) -> Parcel | None: ...
    async def find_parcel(self, user_id: int, tracking_number: str) -> Parcel | None: ...
    async def list_parcels(
        self, user_id: int, *, terminal_since: datetime
    ) -> list[
        Parcel
    ]: ...  # active + terminal with updated_at >= terminal_since; ORDER BY created_at, id
    async def count_active_parcels(self, user_id: int) -> int: ...
    async def active_parcels_for_user(self, user_id: int) -> list[Parcel]: ...
    async def due_parcels(
        self, now: datetime
    ) -> list[
        Parcel
    ]: ...  # active, owner is_allowed=1, next_check_at <= now; ORDER BY next_check_at, id
    async def resolve_carrier(
        self, parcel_id: int, carrier: CarrierCode, now: datetime
    ) -> None: ...  # carrier=?, candidates=carrier
    async def set_label(self, parcel_id: int, label: str | None, now: datetime) -> None: ...
    async def delete_parcel(self, parcel_id: int) -> None: ...
    async def record_check_success(
        self,
        parcel_id: int,
        *,
        state: ParcelState,
        last_status_text: str | None,
        last_event_at: datetime | None,
        next_check_at: datetime,
        now: datetime,
        delivered_at: datetime | None = None,
    ) -> (
        None
    ): ...  # resets consecutive_failures; None for last_* / delivered_at keeps existing value
    async def record_check_failure(
        self, parcel_id: int, *, next_check_at: datetime, now: datetime
    ) -> int: ...  # returns new consecutive_failures
    async def set_state(self, parcel_id: int, state: ParcelState, now: datetime) -> None: ...
    async def delete_terminal_before(self, cutoff: datetime) -> int: ...
    async def count_all_active(self) -> int: ...
    # events
    async def insert_events(
        self, parcel_id: int, events: Sequence[TrackingEvent], now: datetime
    ) -> list[TrackingEvent]: ...  # returns newly inserted, ascending
    async def list_events(
        self, parcel_id: int, limit: int
    ) -> list[TrackingEvent]: ...  # the `limit` most recent, returned ascending
    async def count_events(self, parcel_id: int) -> int: ...
    # meta
    async def get_meta(self, key: str) -> str | None: ...
    async def set_meta(self, key: str, value: str) -> None: ...
```

`add_parcel` raises `DuplicateParcelError` on the UNIQUE constraint.

### 9.9 `services/formatting.py` (pure, no I/O)

```python
def parcel_title(parcel: Parcel) -> str: ...  # escaped label, else tracking number
def carrier_name(code: CarrierCode) -> str: ...  # CARRIER_NAMES (HTML-safe)
def carrier_names(codes: Sequence[CarrierCode]) -> str: ...  # joined with CARRIER_SEPARATOR
def parcel_carrier_label(
    parcel: Parcel,
) -> str: ...  # resolved → carrier_name; else carrier_names(candidates)
def format_time(dt: datetime, tz: ZoneInfo) -> str: ...  # TIME_FORMAT in tz
def format_links(code: str, carriers: Sequence[CarrierCode]) -> str: ...  # §4.4
def format_link_only(code: str, carriers: Sequence[CarrierCode]) -> str: ...  # LINK_ONLY
def format_event_update(
    parcel: Parcel,
    new_events: Sequence[TrackingEvent],
    tz: ZoneInfo,
    *,
    delivered: bool,
    returned: bool,
    resolved_carrier: CarrierCode | None = None,
) -> str: ...
def format_parcel_list(parcels: Sequence[Parcel], tz: ZoneInfo) -> str: ...
def format_history(
    parcel: Parcel, events: Sequence[TrackingEvent], tz: ZoneInfo
) -> str: ...  # newest first
def format_add_outcome(outcome: AddOutcome, tz: ZoneInfo, *, max_parcels: int) -> str: ...
def format_needs_phone_multi(codes: Sequence[str]) -> str: ...
def format_expired(parcel: Parcel) -> str: ...
def format_stale(parcel: Parcel) -> str: ...
def format_carrier_alert(carrier: CarrierCode, count: int, detail: str) -> str: ...
def format_users(users: Sequence[User], active_counts: Mapping[int, int], admin_id: int) -> str: ...
def format_health(
    last_poll_at: datetime | None, report: dict | None, active: int, users: int, tz: ZoneInfo
) -> str: ...
def truncate_message(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> str: ...
```

### 9.10 `services/parcels.py`

```python
AddKind = Literal[
    "added", "needs_phone", "link_only", "duplicate", "limit", "invalid_code", "invalid_phone"
]


@dataclass(frozen=True)
class AddOutcome:
    kind: AddKind
    code: str | None = None  # normalized code when known
    parcel: Parcel | None = None  # refreshed after the first fetch
    result: TrackingResult | None = None  # found result, or the last not-found result
    error: CarrierError | None = None  # set when every attempted fetch failed
    candidates: tuple[CarrierCode, ...] = ()  # needs_phone: carriers still missing digits
    link_carriers: tuple[CarrierCode, ...] = ()  # link-only candidates to mention


class ParcelService:
    def __init__(
        self,
        repo: Repository,
        carriers: Mapping[CarrierCode, Carrier],
        http: httpx.AsyncClient,
        settings: Settings,
        now: Callable[[], datetime],
    ) -> None: ...
    async def add(
        self,
        user: User,
        raw_code: str,
        phone_last4: str | None = None,
        carrier: CarrierCode | None = None,
    ) -> AddOutcome: ...
    async def list_for(self, user_id: int) -> list[Parcel]: ...
    async def resolve(
        self, user_id: int, ref: str
    ) -> Parcel | None: ...  # 1-3 digit ref = 1-based index into list_for; else normalized code
    async def remove(
        self, user_id: int, ref: str
    ) -> Parcel | None: ...  # returns the deleted parcel
    async def rename(self, user_id: int, ref: str, label: str | None) -> Parcel | None: ...
    async def history(
        self, user_id: int, ref: str
    ) -> tuple[Parcel, list[TrackingEvent]] | None: ...
    async def set_default_phone(
        self, user_id: int, last4: str | None
    ) -> None: ...  # ValueError if invalid
```

### 9.11 `services/poller.py`

```python
class Notifier(Protocol):
    async def send(self, chat_id: int, text: str, *, silent: bool = False) -> None: ...


@dataclass(frozen=True)
class FetchKey:
    carrier: CarrierCode
    tracking_number: str
    phone_last4: str | None


def fetch_keys(
    parcel: Parcel, carriers: Mapping[CarrierCode, Carrier]
) -> list[FetchKey]: ...  # §6.2


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
    def __init__(
        self,
        repo: Repository,
        carriers: Mapping[CarrierCode, Carrier],
        http: httpx.AsyncClient,
        notifier: Notifier,
        settings: Settings,
        now: Callable[[], datetime],
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rand: Callable[[], float] = random.random,
    ) -> None: ...
    async def run_cycle(
        self, *, only_user_id: int | None = None, wait: bool = False
    ) -> PollReport: ...
    def is_quiet(self, at: datetime) -> bool: ...
```

### 9.12 `bot/`

```python
# parsing.py
def parse_track_args(args: Sequence[str]) -> tuple[str, str | None, CarrierCode | None] | None:
    ...
    # (code, last4, forced carrier); rules in §4.1


def parse_ref_and_text(args: Sequence[str]) -> tuple[str, str | None] | None: ...


@dataclass(frozen=True)
class TextRoute:
    kind: Literal["phone_for_pending", "codes", "invalid_phone", "unknown"]
    codes: tuple[str, ...] = ()
    last4: str | None = None


def route_text(text: str, has_pending: bool) -> TextRoute: ...


# auth.py
def is_authorized(user: User | None, telegram_id: int, admin_id: int) -> bool: ...
async def gate(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None: ...  # TypeHandler group -1; raises ApplicationHandlerStop
def admin_only(handler): ...  # decorator


# commands.py
BOT_COMMANDS: list[tuple[str, str]]


# notifier.py
class TelegramNotifier:  # implements Notifier
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


def get_deps(context: ContextTypes.DEFAULT_TYPE) -> Deps: ...  # context.bot_data["deps"]


# app.py
def build_application(settings: Settings) -> Application: ...
async def poll_job(context: ContextTypes.DEFAULT_TYPE) -> None: ...
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None: ...


# __main__.py
def main() -> int: ...
```

`parse_track_args` rules: empty → `None`. If `len(args) >= 2` and `parse_carrier_alias(args[-1])` is not `None` → that is the forced carrier; drop it. Then if at least 2 args remain and the last is 4 digits, it is `last4` (drop it) when the forced carrier needs a phone or, without a forced carrier, `detect_carriers(normalize_code("".join(args[:-1])))` contains a carrier that needs a phone. `code = normalize_code("".join(remaining args))`; empty → `None`.

Pending phone question: `context.user_data["pending_phone"] = {"code": str, "carrier": CarrierCode | None}`.

`BOT_COMMANDS`:
```python
[
    ("start", "Bắt đầu"),
    ("help", "Hướng dẫn"),
    ("track", "Theo dõi đơn: /track <mã> [4 số] [hãng]"),
    ("list", "Danh sách đơn"),
    ("status", "Hành trình đơn"),
    ("label", "Đặt tên cho đơn"),
    ("remove", "Ngừng theo dõi"),
    ("phone", "4 số cuối SĐT cho đơn J&T, GHN"),
    ("check", "Kiểm tra ngay"),
    ("cancel", "Hủy thao tác"),
]
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
- **No real network in automated tests.** Live checks live only in `scripts/probe_carriers.py` and the interactive prompts (10A, 11, 13).
- Carrier parsers are tested against the fixtures in `tests/fixtures/<carrier>/`. `FIXTURES.md` records each file's **provenance**: `synthetic` (hand-built in Prompt 2 from the shapes in §5) or `live YYYY-MM-DD` (sanitized capture from Prompt 10A). Parser tests assert the facts written in FIXTURES.md, so replacing a synthetic fixture with a live one only changes those facts.
- Parsers accept the documented variants (snake_case/camelCase keys, epoch or ISO times, several timezone spellings) so that a live response within §5 does not break them.
- Repository tests use a temp-file SQLite DB (`tmp_path`).
- Services are tested with the real `Repository` plus `tests/fakes.py`:
  - `FakeClock` — `now()` returns a settable aware UTC datetime; `advance(timedelta)`.
  - `FakeCarrier(code, *, needs_phone=None, display_name=None)` — `needs_phone` and `display_name` default to the `CATALOG` values; `results: dict[tuple[str, str | None], TrackingResult | CarrierError]`, records `calls: list[tuple[str, str | None]]`; raises the error if the mapped value is a `CarrierError`; unknown key → `TrackingResult(found=False)`.
  - `FakeNotifier` — records `sent: list[tuple[int, str, bool]]`; optional `fail_with: Exception | None`.
- Telegram handlers stay thin; their parsing/authorization logic lives in pure functions (`bot/parsing.py`, `bot/auth.py.is_authorized`) that are unit-tested. The handler wiring is verified by a no-network `build_application` smoke test and the manual E2E run.
- Coverage target: ≥ 85 % for `carrier_catalog`, `tracking_codes`, `carriers`, `db`, `services`.
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
12. Paste a real Cainiao (`LP…`) or 4PX (`4PX…`) code → `ADDED_FOUND` naming Cainiao / 4PX.
13. With `/phone` set, paste a real GHN or Ninja Van code that matches rule 12 (§5.2) → the bot tries the candidates and replies `ADDED_FOUND` naming the right carrier; `/list` shows that carrier.
14. Paste a VNPost-shaped code (`EB123456789VN`) → `LINK_ONLY` with a VNPost link and a 17TRACK link; `/list` unchanged.
15. `/track <real GHN code> <4 digits> ghn` → added as GHN without detection; `/track <12-digit J&T code>` with no data yet → `ADDED_PENDING` plus the BEST / Viettel Post links.
16. Restart the PC and log in → bot running within 1 min; no duplicate notifications for already-seen events.
17. Disconnect the network for 15 min → no crash, no user messages about errors, recovery after reconnection; after 5 consecutive failures admin gets one `ALERT_CARRIER`.
18. Start a second instance manually → it exits immediately with the "another instance" log line.
19. `Select-String -Path logs\* -Pattern <token>` → no matches.

## 15. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | SPX real data needs a signed request whose Vietnamese secret is unknown | High | High | Prompt 10A with real codes; find the secret via DevTools; otherwise the human chooses (headers copy, headless browser, aggregator, or SPX link-only) |
| R2 | J&T phone-digit submission differs from the assumed `cellphone` GET param | Medium | High | Prompt 10A inspects `tracking_cellphone.js` and the verify modal and tests with a real code + digits |
| R3 | Carriers change markup/API or add anti-bot | Medium (over months) | High | Parser errors → backoff + admin alert; fixtures make fixes quick; conservative polling |
| R4 | Telegram blocked by the ISP | Medium | High | Pre-flight check; `TELEGRAM_PROXY_URL` |
| R5 | PC off or asleep | High | Low–Medium | Catch-up cycle on start; auto-start task; power settings |
| R6 | Wrong J&T/GHN phone digits look like "not found" | Medium | Low | Hint on add; `EXPIRED` after 7 days tells the user to check digits |
| R7 | Token leak via logs or commits | Low | High | httpx log level, redact filter, gitignore, acceptance check 19 |
| R8 | Terms-of-use concerns with automated lookups | Low | Medium | Personal, low-volume, honest client, no evasion, no resale; link-only for carriers that deploy anti-bot measures |
| R9 | Duplicate bot instances | Low | Medium | Lock file + `MultipleInstances IgnoreNew` + `Conflict` handling |
| R10 | Timezone errors on Windows | Medium | Low | `tzdata` dependency, aware datetimes enforced by `TrackingEvent` |
| R11 | Synthetic fixtures differ from real responses (SPX found data, J&T markup, Cainiao, 4PX, Ninja Van, GHN) | High | Medium | Parsers accept documented variants; Prompt 10A replaces fixtures with live captures and fixes parsers test-first |
| R12 | Detection rules misattribute a code (several formats come from web sources) | Medium | Medium | Auto-try across candidates; forced carrier alias in `/track`; Prompt 10A corrects §5.2 |
| R13 | Unresolved parcels double the requests for their code | Low | Low | At most two candidates per rule; 7-day pending expiry |
| R14 | A link-only carrier's link template stops working | Medium | Low | Every link list also carries a 17TRACK link |

## 16. Out of scope for v1 (future ideas)

- Auto-import codes from Gmail (Shopee/TikTok/Lazada emails) or a marketplace account.
- Polling link-only carriers (BEST Express, YunExpress, GHTK, Viettel Post, VNPost, LEX VN): would need captcha solving, headless browsers, or a paid aggregator (17TRACK API). A carrier moves to tracked only when an open endpoint is found (Appendix B).
- Following a cross-border parcel's hand-off to a Vietnamese last-mile code automatically (Cainiao/4PX → SPX/J&T/Ninja Van).
- Batched lookups (J&T accepts up to 10 codes; 4PX and Cainiao accept lists) — only worth it at larger volumes.
- Inline buttons on notifications (remove/label), per-user "milestones only" mode, English UI.
- Group-chat mode, web dashboard, VPS/cloud hosting, DB backups (data is short-lived).

---

## 17. Text catalog (`texts.py`)

All messages are sent with `parse_mode=HTML`. `{placeholders}` are filled with **already-escaped** values by `services/formatting.py`. Copy verbatim.

```python
TIME_FORMAT = "%d/%m %H:%M"

CARRIER_NAMES = {
    "spx": "SPX",
    "jt": "J&amp;T",
    "cainiao": "Cainiao",
    "fourpx": "4PX",
    "ninjavan": "Ninja Van",
    "ghn": "GHN",
    "best": "BEST Express",
    "yunexpress": "YunExpress",
    "ghtk": "GHTK",
    "viettelpost": "Viettel Post",
    "vnpost": "VNPost",
    "lex": "LEX VN",
}
CARRIER_UNRESOLVED = "Đang xác định hãng"
CARRIER_SEPARATOR = " / "

STATE_EMOJI = {
    "pending": "⏳",
    "in_transit": "🚚",
    "delivered": "✅",
    "returned": "↩️",
    "expired": "⌛",
    "stale": "⚠️",
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
    "Mình sẽ nhắn cho bạn mỗi khi đơn hàng có cập nhật mới.\n"
    "Gửi mã vận đơn để bắt đầu, mình sẽ tự nhận diện hãng vận chuyển."
)
HELP = (
    "<b>📦 Hướng dẫn</b>\n"
    "• Gửi mã vận đơn để theo dõi, mình tự nhận diện hãng\n"
    "• Tự động theo dõi: SPX, J&amp;T, Cainiao, 4PX, Ninja Van, GHN\n"
    "• Gửi link tra cứu: BEST Express, YunExpress, GHTK, Viettel Post, VNPost, LEX VN\n"
    "• /track &lt;mã&gt; [4 số cuối SĐT] [hãng] – theo dõi đơn (hãng: spx, jt, cainiao, 4px, ninjavan, ghn)\n"
    "• /list – các đơn đang theo dõi\n"
    "• /status &lt;mã hoặc số thứ tự&gt; – xem hành trình\n"
    "• /label &lt;mã hoặc số thứ tự&gt; &lt;tên&gt; – đặt tên cho đơn\n"
    "• /remove &lt;mã hoặc số thứ tự&gt; – ngừng theo dõi\n"
    "• /phone &lt;4 số&gt; – lưu 4 số cuối SĐT cho đơn J&amp;T, GHN (/phone clear để xóa)\n"
    "• /check – kiểm tra ngay\n"
    "• /cancel – hủy thao tác đang chờ"
)
NOT_ALLOWED = (
    "🔒 Bạn chưa có quyền dùng bot này.\nHãy gửi ID sau cho người quản lý: <code>{user_id}</code>"
)
ADMIN_ONLY = "🔒 Lệnh này chỉ dành cho người quản lý."
UNKNOWN_COMMAND = "Mình không hiểu lệnh này. Gõ /help để xem hướng dẫn."
UNKNOWN_CODE = (
    "🤔 Mình không nhận ra mã vận đơn nào.\n"
    "Gõ /help để xem các hãng được hỗ trợ, hoặc dùng /track &lt;mã&gt; &lt;hãng&gt;."
)
ERROR_GENERIC = "😵 Có lỗi xảy ra, bạn thử lại sau nhé."

USAGE_TRACK = "Cách dùng: /track &lt;mã&gt; [4 số cuối SĐT] [hãng]"
USAGE_REF = "Cách dùng: /{command} &lt;mã hoặc số thứ tự trong /list&gt;"
USAGE_LABEL = "Cách dùng: /label &lt;mã hoặc số thứ tự&gt; &lt;tên&gt; (bỏ trống tên để xóa)"

ASK_PHONE = (
    "📱 Mã <code>{code}</code> ({carriers}) cần 4 số cuối SĐT người nhận.\n"
    "Gửi 4 số đó, hoặc /cancel để hủy."
)
INVALID_PHONE = "Vui lòng nhập đúng 4 chữ số."
NEEDS_PHONE_MULTI = (
    "📱 Các đơn sau cần 4 số cuối SĐT người nhận. "
    "Hãy thêm từng đơn bằng /track &lt;mã&gt; &lt;4 số&gt;:\n{codes}"
)

ADDED_FOUND = "✅ Đã theo dõi <b>{title}</b> · {carrier}\nTrạng thái hiện tại: {status}\n🕒 {time}"
ADDED_DELIVERED = "✅ Đã thêm <b>{title}</b> · {carrier} — đơn này đã giao thành công.\n🕒 {time}"
ADDED_PENDING = (
    "✅ Đã thêm <b>{title}</b> · {carrier}\n"
    "Hiện chưa có thông tin vận chuyển, mình sẽ kiểm tra lại định kỳ."
)
ADDED_PENDING_AUTO = (
    "✅ Đã thêm <b>{title}</b>\n"
    "Hiện chưa có thông tin vận chuyển. Mình sẽ tự kiểm tra mã này ở {carriers}."
)
ADDED_PENDING_PHONE_HINT = "\nNếu vài giờ nữa vẫn chưa có dữ liệu, hãy kiểm tra lại 4 số cuối SĐT."
ADDED_ERROR = (
    "✅ Đã thêm <b>{title}</b> · {carrier}\n"
    "Hiện chưa kết nối được với {carrier}, mình sẽ thử lại sau."
)
DUPLICATE = "Bạn đã theo dõi đơn <code>{code}</code> rồi."
LIMIT_REACHED = "Bạn đang theo dõi tối đa {max} đơn. Hãy /remove bớt đơn cũ nhé."

LINK_ONLY = (
    "🔗 Mã <code>{code}</code> có thể là đơn {carriers}.\n"
    "Mình chưa tự theo dõi được hãng này, bạn xem hành trình tại:\n{links}"
)
LINK_EXTRA = "\n\nNếu đây là đơn {carriers}, xem tại:\n{links}"
LINK_ITEM = '• <a href="{url}">{name}</a>'
LINK_17TRACK_NAME = "17TRACK"

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
UPDATE_RESOLVED = "🔎 Đã xác định hãng vận chuyển: <b>{carrier}</b>"
UPDATE_LINE = "• {time} — {description}"
UPDATE_LOCATION = " ({location})"
UPDATE_MORE = "… và {count} cập nhật trước đó"
UPDATE_DELIVERED = "✅ <b>Đã giao thành công!</b>"
UPDATE_RETURNED = "↩️ <b>Đơn đang được hoàn về người gửi.</b>"

EXPIRED = (
    "⌛ Sau 7 ngày vẫn chưa có dữ liệu cho <code>{code}</code>, mình đã ngừng theo dõi.\n"
    "Hãy kiểm tra lại mã vận đơn (và 4 số cuối SĐT nếu là đơn J&amp;T hoặc GHN)."
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
