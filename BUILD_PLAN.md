# vn-parcel-bot — Build Plan

Version 1.7 · 2026-09-14 · Status: v1 built on branch main; live verification in progress

One self-contained document for building a Telegram bot that notifies a small allowlisted group about parcels bought online in Vietnam. **SPX, J&T, Cainiao, 4PX, Ninja Van and GHN** parcels are tracked automatically; codes from **BEST Express, YunExpress, GHTK, Viettel Post, VNPost and LEX VN** are recognised and answered with tracking links. Hand it to any coding agent (Antigravity `agy`, Claude Code, Gemini CLI, Codex, …) running inside the repository.

| Part | Contents | Used by |
|---|---|---|
| 1. Guide | Changes, progress tracker, how to run prompts, standing rules | You and agents |
| 2. Specification (§1–§17) | What to build — the binding source of truth | Agents: read fully before coding |
| 3. Prompts (0–13, 5A, 5B, 10A) | Step-by-step build prompts | Agents, one prompt per run |
| 4. Appendices (A–D) | Maintenance prompts, troubleshooting, spec coverage map | You and agents |

Citation conventions used everywhere in this file: `§N` = a section of Part 2; `Prompt N` = Part 3; `Appendix X` = Part 4. If code and Part 2 disagree, Part 2 wins; if Part 2 is wrong, fix Part 2 first (in the same commit), then the code.

- Repo: `C:\Users\hozkg\projects\vn-parcel-bot` — this file lives at its root as `BUILD_PLAN.md`; `SPEC.md` is a generated copy of Part 2 (never edit it by hand)
- Shell: Windows PowerShell 5.1 (no `&&`; use `;` or `if ($?) { … }`)
- Python: 3.13 in `.venv`

## Changes in 1.1 (2026-09-13)

- **Ten more carriers** (§5.1). Cainiao, 4PX, Ninja Van and GHN are tracked through their public JSON endpoints. BEST Express, YunExpress, GHTK, Viettel Post, VNPost and LEX VN are link-only: their sites use captchas, a cloud firewall or anti-bot challenges (probed from this PC on 2026-09-13), and v1 does not work around those.
- **Automatic carrier detection with auto-try** (§4.3, §5.2, §6.2). A code can match several carriers; the bot fetches each tracked candidate in order and keeps the first one that returns data. A parcel may stay "carrier unresolved" until data appears.
- **Phone digits for any carrier that needs them** (J&T and GHN), not only J&T.
- **SPX correction** (§5.3): the sibling SPX Thailand client signs `sls_tracking_number`; whether SPX Vietnam needs the same is decided with real codes.
- **Build order**: offline prompts use synthetic fixtures shaped like the researched responses; live verification moved from Prompt 2 to **Prompt 10A**, which gates Prompt 11.

## Changes in 1.7 (2026-09-14)

- **Lazada Cainiao codes** (§5.2, §17): Lazada shows Cainiao parcels as `<15-digit order number>_<waybill>`. `normalize_code` drops the order-number prefix, tokens keep underscores, and `YT` + 13 digits is a Cainiao waybill tracked on Cainiao. On 2026-09-14 Cainiao's public endpoint had no events yet for a real one; pending replies add `LAZADA_CAINIAO_HINT`.
- **Screenshot model** (§10): `VISION_MODEL` defaults to `sonnet`; Haiku misread long Lazada codes in tests.

## Changes in 1.6 (2026-09-14)

- **J&T cross-border codes** (§5.2, §17): `JNTX…` waybills (J&T International Logistics, e.g. Lazada cross-border orders delivered by J&T VN) are detected as J&T and tracked on J&T VN like 12-digit codes. On 2026-09-14 J&T VN had no data for a real JNTX code, J&T International VN only accepts codes starting with 44, and J&T China's international lookup requires a captcha (not used). Replies add `JT_CROSS_BORDER_HINT` pointing to the Lazada app until J&T VN has data.

## Changes in 1.5 (2026-09-14)

- **Daily digests** (§6, §10, §17): at each `DIGEST_TIMES` slot every allowed user with parcels gets a summary with 🆕 on parcels that changed since their previous digest. Details and tests: `docs/superpowers/specs/2026-09-14-spx-browser-vision-digests-design.md` §5.

## Changes in 1.4 (2026-09-14)

- **Screenshots** (§4.5, §9.10, §9.12, §10, §17): photos and image documents are read by a vision engine, Claude Code on this PC by default or the Anthropic API as a backup; the parcel is added with the product name as its label. Details and tests: `docs/superpowers/specs/2026-09-14-spx-browser-vision-digests-design.md` §4.

## Changes in 1.3 (2026-09-14)

- **SPX endpoint** (§5.1, §5.3, §9, R1): the bot reads `get_order_info`, the endpoint spx.vn's own tracking page loads the timeline from. The old `fleet_order/tracking/search` endpoint returned `data: {}` for a real code that spx.vn showed as out for delivery. A plain request works; signing, `SPX_SIGNING_SECRET` and `sign_spx_code` are removed. Part 3 prompts that mention SPX signing are historical; Part 2 wins.

## Changes in 1.2 (2026-09-14)

- **Detection without carrier names** (§4.1, §4.3, §5.2): the `/track <mã> <hãng>` alias override is removed; every code is recognised automatically. Extra words after a code are ignored.
- **New formats seen in real use:** BEST Express `BEST…VN…` codes (link-only). 14-digit `84…` codes are TikTok Shop seller own fleet codes with no public tracking: `SELLER_FLEET` reply, nothing stored. A live check on 2026-09-14 found no J&T data for one, and J&T's own examples are 12 digits.
- **Order numbers and unknown codes:** 15-digit numbers are treated as marketplace order numbers (`ORDER_NUMBER` reply), and any other code-like input gets a 17TRACK link (`UNKNOWN_CARRIER` reply) instead of "not recognised". Unrecognised codes are logged masked so new formats can be added.
- Part 3 prompts describe the original 1.1 build steps; where they mention carrier aliases or `GENERIC_CODE_RE`, Part 2 wins.

---

## Progress

| # | Prompt | Needs from you | Done |
|---|---|---|---|
| 0 | Pre-flight (you, ~20 min) | BotFather, Telegram ID, real codes | [ ] |
| 1 | Scaffold, settings, logging | – | [x] |
| 2 | HTTP client, carrier helpers, probe script, synthetic fixtures | – | [x] |
| 3 | Carrier catalog, tracking codes, tracking models | – | [x] |
| 4 | SPX carrier | – | [x] |
| 5 | J&T carrier | – | [x] |
| 5A | Cainiao and 4PX carriers | – | [x] |
| 5B | Ninja Van and GHN carriers, carrier registry | – | [x] |
| 6 | Database schema and repository | – | [x] |
| 7 | Texts and message formatting | – | [x] |
| 8 | Parcel service (auto-try) | – | [x] |
| 9 | Poller | – | [x] |
| 10 | Telegram bot layer and entry point | – | [x] |
| 10A | Live carrier check — **GATE** | `.env`, `probe_codes.local.txt` | [ ] |
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
| `/track` | `<code> [last4]` | Add a parcel (§4.3); the carrier is always detected automatically. The code may contain spaces/dashes (`/track SPXVN 0533 8454 932C`). A trailing 4-digit argument is the phone override only when the remaining code has a candidate that needs a phone; otherwise it stays part of the code. If the joined arguments are not a recognised code, order number or seller fleet code, the first code found by `extract_codes` in them is used, so extra words are ignored. No args → `USAGE_TRACK`. |
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
- **Several codes** → add each with no phone override. `needs_phone` outcomes are not stored and are listed once in `NEEDS_PHONE_MULTI`; every other outcome gets its own reply. No pending question is created for multi-code messages.

### 4.3 Adding a parcel (`ParcelService.add`)

Inputs: the user, the raw code, an optional phone override. A candidate counts as **tracked** only if it is tracked in §5.1 **and** present in the service's carrier mapping.

1. `code = normalize_code(raw)`; candidates = `detect_carriers(code)`. No candidates → `seller_fleet` if `is_seller_fleet(code)`, else `order_number` if `is_order_number(code)`, else `unknown_carrier` if `is_code_like(code)`, else `invalid_code`. Nothing is stored and no request is made; `seller_fleet`, `order_number` and `unknown_carrier` are logged at INFO with the masked code and its length.
2. Split candidates, preserving order, into `tracked` (tracked in §5.1 and present in the carrier mapping) and `link_only` (link-only in §5.1). Tracked carriers missing from the mapping are dropped. Both lists empty → `invalid_code`.
3. A phone override that fails `is_valid_last4` → `invalid_phone`.
4. `tracked` empty → `link_only` outcome with `link_carriers = link_only`. Nothing stored, no request.
5. The user already has a parcel with this tracking number (any carrier, any state) → `duplicate`. The user already has `max_parcels_per_user` (30) **active** parcels → `limit`.
6. `last4 = override or user.default_phone_last4`. `tryable` = tracked candidates that do not need a phone, plus those that do when `last4` is set. `phone_missing` = tracked candidates that need a phone while `last4` is `None`.
7. Fetch the `tryable` candidates **one by one in order**, stopping at the first result with `found=True`. A `CarrierError` is remembered and the next candidate is tried.
8. **Found** with carrier `c` → insert the parcel with `carrier=c`, `candidates=(c,)`, `phone_last4 = last4 if c needs a phone else None`, `next_check_at = now + poll_interval`; insert all events silently; set state (`delivered` / `returned` / `in_transit`); outcome `added` with the result. Reply `ADDED_FOUND` or `ADDED_DELIVERED`.
9. **Not found and `phone_missing` non-empty** → `needs_phone` with `candidates = phone_missing` (nothing stored). The handler stores `context.user_data["pending_phone"] = {"code": code}` and replies `ASK_PHONE`. The next 4-digit message calls `add` again with those digits (all tryable candidates are fetched again).
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

### 4.5 Screenshots (`photo_message`)

- A photo or image document in a private chat goes to the vision engine chosen by `VISION_ENGINE` (§10), one photo at a time per user. Documents that are not JPEG/PNG/WebP/GIF or exceed `VISION_MAX_IMAGE_BYTES` (5 MB) get `VISION_UNSUPPORTED_IMAGE` without downloading.
- `claude_code` (default): `claude -p --input-format stream-json --output-format stream-json --verbose --model <VISION_MODEL> --tools "" --no-session-persistence --strict-mcp-config --setting-sources project` in an empty temporary directory, image as a base64 block on stdin, no console window, one call at a time, `VISION_TIMEOUT_SECONDS`. `api`: the same content to the Anthropic Messages API. Both parse the reply with `parse_vision_text` (JSON with `tracking_codes`, `order_ids`, `carrier`, `product_names`, `phone_last4`; free text falls back to `extract_codes`).
- Error codes: `not_configured` → `VISION_NOT_CONFIGURED`; `timeout`, `cli_error`, `http_status`, `network`, `invalid_response` → `VISION_ERROR`. Logs hold error codes, exit codes and durations only.
- Shipping codes → the add flow (§4.3) with `label` = the product name (first item, ` +N` for more items, at most 40 characters); a duplicate parcel gets the label only if it has none; a pending phone question keeps the label. Replies start with `VISION_DETECTED_HEADER` and `VISION_PRODUCT`.
- Only an order number → `VISION_ORDER_ONLY`, nothing stored. Nothing found → `VISION_NO_DATA`.

## 5. Carriers

### 5.1 Catalog

Facts probed from this PC on 2026-09-13 with fake codes unless marked otherwise.

| Code | Name | Tier | Needs phone | Evidence | Official link template |
|---|---|---|---|---|---|
| `spx` | SPX | tracked | no | JSON endpoint used by spx.vn's tracking page; verified with a real code 2026-09-14 (§5.3) | – |
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

### 5.2 Code normalization, detection, order numbers and fallback

- `normalize_code(raw)`: uppercase; remove all whitespace and `-`; strip surrounding `,;:()[]<>"'.`. Internal dots are kept (GHTK codes contain them).
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
| 10 | `^JNTX[A-Z]?\d{8,12}$` | jt | observed (`JNTXB…`, Lazada cross-border via J&T VN) |
| 11 | `^YT\d{13}$` | cainiao | observed (Lazada `<order>_YT…` shown as Cainiao) |
| 12 | `^BEST[A-Z]{0,6}\d{8,16}VN[A-Z]{0,3}$` | best | observed (`BESTMP…VNA`) |
| 13 | `^\d{12}$` | jt, best, viettelpost | observed (J&T); web |
| 14 | `^\d{13}$` | best | web |
| 15 | `^(?=[0-9A-Z]*[A-Z])(?=[0-9A-Z]*\d)[0-9A-Z]{8,14}$` | ghn, ninjavan | web; unprefixed alphanumeric codes |

  No rule matches → `[]`.
- `is_order_number(code)`: `^\d{15}$`. Marketplace order numbers (Lazada, TikTok Shop) have this shape; they are not shipping codes and are never tracked.
- Lazada composite codes: after upper-casing and removing spaces/dashes, `normalize_code` turns `^\d{15}_([0-9A-Z]{8,30})$` into the part after the underscore (the waybill). `extract_codes` tokens may contain `_` so the composite stays one token.
- `is_lazada_cainiao(code)`: `^YT\d{13}$` (rule 11); pending add replies append `LAZADA_CAINIAO_HINT`.
- `is_jt_cross_border(code)`: `^JNTX[A-Z]?\d{8,12}$` (rule 10). Such parcels are J&T parcels; add replies (pending and phone question) append `JT_CROSS_BORDER_HINT`.
- `is_seller_fleet(code)`: `^84\d{12}$`. TikTok Shop seller own fleet codes; no public tracking page, never tracked.
- `is_code_like(code)`: `^[0-9A-Z]{8,40}$` with at least 6 digits.
- `extract_codes(text)`: iterate `re.finditer(r"[0-9A-Za-z][0-9A-Za-z.\-]*[0-9A-Za-z]", text)` and normalize each token. **Known** tokens: a rule match (a **rule 15** match only when the whole stripped message is that single token), an order number or a seller fleet code. **Fallback** tokens: other code-like tokens, including rule-15 matches inside longer text. Return the known tokens if there are any, else the fallback tokens; order of appearance, de-duplicated. No joining of space-separated fragments.
- `is_valid_last4(s)`: `^\d{4}$`.
- `mask_code(code)`: `code[:5] + "…" + code[-3:]`, used in logs.

Prompt 10A updates this section and `tracking_codes.py` together when real codes contradict a rule.

### 5.3 SPX Express Vietnam

| Item | Value | Confidence |
|---|---|---|
| Endpoint | `GET https://spx.vn/shipment/order/open/order/get_order_info?language_code=vi&spx_tn=<CODE>`, the call spx.vn's tracking page makes | Verified with a real code (2026-09-14): plain request, no signature or page headers |
| Unknown code | `{"retcode": 2, "message": "…find [0]:get logistic order index map error", "data": {}}` | Verified (2026-09-14) |
| Found response | `retcode 0`; `data.sls_tracking_info.records[]`, newest first, with `actual_time` (int, Unix seconds), `description`, `tracking_code` (`F980` delivered, `F600` out for delivery), `milestone_code` (int; `8` delivered), `milestone_name`, `tracking_name`, `display_flag` (`1` = shown on spx.vn), `current_location.location_name` | Verified (2026-09-14) |
| Personal data | The same response carries `receiver_name`, `driver_phone_number`, `client_order_id`, `buyer_description`, `epod`, addresses and coordinates | Never read, stored, logged or put in fixtures |
| Old endpoint | `GET https://spx.vn/api/v2/fleet_order/tracking/search` returns `data: {}` for real codes | Not used |

- Parsing: payload not an object or without `retcode` → `parse` error. `retcode` in `NOT_FOUND_RETCODES = (2,)` → not found; any other non-zero `retcode` → `parse` error. `data` missing/empty, `sls_tracking_info` missing, or `records` missing/empty → not found. `sls_tracking_info` not an object or `records` not a list → `parse` error.
- Records with `display_flag != 1` are skipped. A kept record that is not an object, lacks an integer `actual_time` (bool rejected) or has an empty `description` after whitespace collapsing → `parse` error. No kept records → not found.
- Event: `time = datetime.fromtimestamp(actual_time, UTC)`; `description` whitespace-collapsed; `location` = whitespace-collapsed `current_location.location_name` only when non-empty and not already contained in the description (case-insensitive), else `None`; `raw_status = tracking_code`.
- `delivered` = the latest kept record has `milestone_code == 8` or `tracking_code == "F980"`. `returned` = not delivered and any of `return`, `hoàn hàng`, `trả hàng` (casefold substring) in that record's `description`, `tracking_name` or `milestone_name`.

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

### Daily digests (`services/digest.py`)

- `schedule_jobs` registers one `JobQueue.run_daily(digest_job, time=<slot with TIMEZONE>)` per `DIGEST_TIMES` slot (default `07:00,12:00,19:00,22:00`; empty disables) next to the poll job and logs `digests scheduled at …`. A slot missed while the bot is down is skipped.
- `DigestService.send_all`: `cutoff = now()` once, before any query; for every user with `is_allowed`, `build(user_id, cutoff)` and send with sound (`silent=False`). After a successful send `meta["digest:last:<user_id>"] = cutoff`; a failed send leaves it unchanged; a `Forbidden` handled by the notifier counts as sent.
- `build`: `since` = the stored cutoff or `cutoff - FIRST_DIGEST_WINDOW` (24 h); parcels = `list_parcels(user_id, terminal_since=since)`; none → no message. Lines use the `/list` layout (`LIST_ITEM`) with `DIGEST_NEW_MARK` when the parcel has events saved since `since` (`parcel_ids_with_events_since`) or is terminal. Header `DIGEST_HEADER` with the local `HH:MM`, footer `DIGEST_FOOTER` plus `DIGEST_FOOTER_FINISHED` when parcels finished.
- Instant update messages and quiet hours are unchanged.

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
     carrier_catalog.py + tracking_codes.py (pure: tiers, links, detection)
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
│  ├─ carrier_catalog.py        CarrierCode, CarrierInfo, CATALOG, links
│  ├─ tracking_codes.py         normalize/detect/extract codes
│  ├─ carriers/
│  │  ├─ __init__.py            CARRIERS registry, get_carrier
│  │  ├─ models.py              TrackingEvent, TrackingResult, CarrierError, Carrier protocol
│  │  ├─ http.py                DEFAULT_HEADERS, make_http_client
│  │  ├─ common.py              request, json_body, looks_like_challenge, parse_gmt_offset, clean_text
│  │  ├─ spx.py                 parse_spx_response, SpxCarrier
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


# tracking_codes.py
def normalize_code(raw: str) -> str: ...
def detect_carriers(code: str) -> list[CarrierCode]: ...
def is_order_number(code: str) -> bool: ...
def is_seller_fleet(code: str) -> bool: ...
def is_jt_cross_border(code: str) -> bool: ...
def is_lazada_cainiao(code: str) -> bool: ...
def is_code_like(code: str) -> bool: ...
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
SPX_ORDER_INFO_URL = "https://spx.vn/shipment/order/open/order/get_order_info"
NOT_FOUND_RETCODES = (2,)
PUBLIC_DISPLAY_FLAG = 1
DELIVERED_MILESTONE = 8
DELIVERED_TRACKING_CODES = ("F980",)
RETURNED_MARKERS = ("return", "hoàn hàng", "trả hàng")
def parse_spx_response(payload: object, tracking_number: str) -> TrackingResult: ...
class SpxCarrier:  code = "spx"; display_name = "SPX"; needs_phone = False
    # fetch: GET SPX_ORDER_INFO_URL with params {"language_code": "vi", "spx_tn": code}

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
    "added",
    "needs_phone",
    "link_only",
    "seller_fleet",
    "order_number",
    "unknown_carrier",
    "duplicate",
    "limit",
    "invalid_code",
    "invalid_phone",
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
        label: str | None = None,
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
def parse_track_args(args: Sequence[str]) -> tuple[str, str | None] | None:
    ...
    # (code, last4); rules below


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

`parse_track_args` rules: blank args are dropped; none left → `None`. If at least 2 args remain, the last is 4 digits, and `detect_carriers(normalize_code("".join(args[:-1])))` contains a carrier that needs a phone → it is `last4` (drop it). `joined = normalize_code("".join(remaining args))`; if `detect_carriers(joined)` is non-empty or `is_order_number(joined)` or `is_seller_fleet(joined)` → `(joined, last4)`; else the first result of `extract_codes(" ".join(remaining args))` if any; else `(joined, last4)`.

Pending phone question: `context.user_data["pending_phone"] = {"code": str, "label": str | None}`.

`BOT_COMMANDS`:
```python
[
    ("start", "Bắt đầu"),
    ("help", "Hướng dẫn"),
    ("track", "Theo dõi đơn: /track <mã> [4 số cuối SĐT]"),
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
| `VISION_ENGINE` | no | `claude_code` | `claude_code` or `api` |
| `CLAUDE_CODE_PATH` | no | `claude` on `PATH`, else `%USERPROFILE%\.local\bin\claude.exe` | path to the Claude Code executable |
| `VISION_MODEL` | no | `sonnet` | Claude Code model alias or id |
| `VISION_TIMEOUT_SECONDS` | no | `90` | 10..300 |
| `ANTHROPIC_API_KEY` | no | – | `api` engine only |
| `ANTHROPIC_MODEL` | no | `claude-haiku-4-5-20251001` | `api` engine only |
| `ANTHROPIC_WORKSPACE_ID` | no | – | `api` engine only, for keys not scoped to a workspace |
| `DIGEST_TIMES` | no | `07:00,12:00,19:00,22:00` | comma-separated local HH:MM; empty disables |

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
13. With `/phone` set, paste a real GHN or Ninja Van code that matches rule 15 (§5.2) → the bot tries the candidates and replies `ADDED_FOUND` naming the right carrier; `/list` shows that carrier.
14. Paste a VNPost-shaped code (`EB123456789VN`) → `LINK_ONLY` with a VNPost link and a 17TRACK link; `/list` unchanged.
15. Paste a 15-digit marketplace order number → `ORDER_NUMBER` with a 17TRACK link, nothing added; paste a 14-digit `84…` code → `SELLER_FLEET`; paste an unrecognised code-like string → `UNKNOWN_CARRIER`; `/track <12-digit J&T code>` with no data yet → `ADDED_PENDING` plus the BEST / Viettel Post links.
16. Restart the PC and log in → bot running within 1 min; no duplicate notifications for already-seen events.
17. Disconnect the network for 15 min → no crash, no user messages about errors, recovery after reconnection; after 5 consecutive failures admin gets one `ALERT_CARRIER`.
18. Start a second instance manually → it exits immediately with the "another instance" log line.
19. `Select-String -Path logs\* -Pattern <token>` → no matches.

## 15. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | SPX changes or blocks the order-info endpoint its tracking page uses | Medium | High | Resolved 2026-09-14: the page's own endpoint answers plain requests (§5.3); blocks surface as `blocked` with backoff and admin alerts, replies keep the spx.vn link; no evasion |
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
| R12 | Detection rules misattribute a code (several formats come from web sources) | Medium | Medium | Auto-try across candidates; unrecognised codes get a 17TRACK link and are logged masked; Prompt 10A corrects §5.2 |
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
    "• Gửi ảnh chụp đơn hàng – mình tự đọc mã vận đơn và tên sản phẩm\n"
    "• Tự động theo dõi: SPX, J&amp;T, Cainiao, 4PX, Ninja Van, GHN\n"
    "• Gửi link tra cứu: BEST Express, YunExpress, GHTK, Viettel Post, VNPost, LEX VN\n"
    "• /track &lt;mã&gt; [4 số cuối SĐT] – theo dõi đơn\n"
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
UNKNOWN_CODE = "🤔 Mình không nhận ra mã vận đơn nào.\nGõ /help để xem các hãng được hỗ trợ."
ERROR_GENERIC = "😵 Có lỗi xảy ra, bạn thử lại sau nhé."

USAGE_TRACK = "Cách dùng: /track &lt;mã&gt; [4 số cuối SĐT]"
SELLER_FLEET = (
    "🛵 <code>{code}</code> có vẻ là mã đơn <b>người bán tự giao</b> (TikTok Shop…), "
    "không có trang tra cứu công khai.\n"
    "Hãy xem hành trình trong app nơi bạn đặt hàng. Hoặc thử tra cứu tại:\n{links}"
)
ORDER_NUMBER = (
    "🧾 <code>{code}</code> có vẻ là <b>mã đơn hàng</b>, không phải mã vận đơn.\n"
    "Trong app (Lazada, TikTok Shop, Shopee…) mở đơn → <b>Thông tin vận chuyển</b> "
    "để lấy mã vận đơn rồi gửi cho mình. Hoặc thử tra cứu tại:\n{links}"
)
UNKNOWN_CARRIER = (
    "🔍 Mình chưa nhận ra hãng vận chuyển của mã <code>{code}</code>.\n"
    "Bạn có thể tra cứu tại:\n{links}"
)
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
JT_CROSS_BORDER_HINT = (
    "\n🌏 Đây là đơn quốc tế của J&amp;T: J&amp;T VN chỉ có dữ liệu sau khi hàng "
    "thông quan về Việt Nam. Trong lúc chờ, bạn xem hành trình trong app Lazada nhé."
)
LAZADA_CAINIAO_HINT = (
    "\n🌏 Đơn quốc tế Lazada qua Cainiao: Cainiao có thể chưa công bố hành trình ngay. "
    "Trong lúc chờ, bạn xem hành trình trong app Lazada nhé."
)
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

VISION_NOT_CONFIGURED = (
    "📷 Tính năng đọc ảnh chưa sẵn sàng trên máy chạy bot. Bạn gửi mã vận đơn trực tiếp nhé."
)
VISION_NO_DATA = (
    "🤔 Mình không tìm thấy mã vận đơn hay mã đơn hàng nào trong ảnh này.\n"
    "Bạn thử chụp màn hình <b>Thông tin vận chuyển</b> rõ hơn hoặc gửi mã trực tiếp nhé."
)
VISION_DETECTED_HEADER = "📷 <b>Nhận diện từ hình ảnh:</b>"
VISION_PRODUCT = "• Sản phẩm: <b>{name}</b>"
VISION_DETECTED_ITEM = "• Mã vận đơn: <code>{code}</code>{carrier_suffix}"
VISION_DETECTED_PHONE = "• SĐT người nhận: <code>***{phone}</code>"
VISION_ORDER_ONLY = (
    "🧾 Tìm thấy mã đơn hàng: <code>{order_id}</code>\n"
    "Đây là <b>mã đơn hàng</b>, không phải mã vận đơn.\n"
    "Trong app (Shopee, Lazada, TikTok Shop…) mở đơn → <b>Thông tin vận chuyển</b> "
    "rồi gửi ảnh chụp hoặc mã vận đơn cho mình nhé! Hoặc thử tra cứu tại:\n{links}"
)
VISION_ERROR = (
    "⚠️ Không phân tích được hình ảnh lúc này. Bạn thử lại sau hoặc gửi mã vận đơn trực tiếp nhé."
)
VISION_UNSUPPORTED_IMAGE = (
    "📷 Ảnh này quá lớn hoặc không đúng định dạng. Bạn gửi lại dưới dạng ảnh (không phải tệp) nhé."
)

DIGEST_HEADER = "🗓 <b>Tóm tắt đơn hàng</b> · {time}"
DIGEST_NEW_MARK = " 🆕"
DIGEST_FOOTER = "Đang theo dõi {active} đơn"
DIGEST_FOOTER_FINISHED = " · {finished} đơn vừa kết thúc"
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
- [ ] **0.4 Collect real tracking codes** — needed only for Prompt 10A; the build starts without them. In Shopee / Lazada / TikTok Shop / AliExpress / Temu → order → shipping information, collect as many as you can:
  - SPX (`SPXVN…`): one **in transit** and one **delivered**
  - J&T (12 digits, usually starting `84`): one in transit and one delivered, each with the **last 4 digits of the recipient's phone**
  - Cainiao (`LP…`), 4PX (`4PX…`), Ninja Van (`SPEVN…` or other), GHN (with the last 4 digits): any state
  - a returned/cancelled parcel of any carrier, and one code from a link-only carrier (e.g. VNPost `…VN`, BEST) to check detection
- [ ] **0.5 Power settings.** *Settings → System → Power & sleep → Sleep: Never (when plugged in)*, or accept gaps while the PC sleeps.
- [ ] **0.6 Tools** (already verified on 2026-09-11): Python 3.13.5, git 2.50.1, `agy` 1.2.1.

Keep the token, your ID, the proxy URL, and the codes handy for Prompts 1 and 10A. **Do not paste the token into an agent prompt**; you will type it into `.env` yourself.

---

## Prompt 1 — Scaffold, settings, logging

**Goal:** A clean, installable Python project with validated settings, safe logging, policy constants, and green quality gates.

**Spec:** §8.1, §9.1–9.3, §10, §11, §13.

**Preconditions:** Repo contains only `BUILD_PLAN.md`, `SPEC.md` (generated copy of Part 2) and `.git`.

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
   description = "Telegram bot that tracks parcels bought online in Vietnam"
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

## Prompt 2 — HTTP client, carrier helpers, probe script, synthetic fixtures

**Goal:** The shared HTTP client and carrier helpers, a probe script ready for Prompt 10A, and synthetic fixtures for every tracked carrier so the offline build proceeds without real codes.

**Spec:** §5 (all), §9.7 (`http.py`, `common.py`), §11 (sanitization), §13.

**Preconditions:** Prompt 1 committed. No `.env` or real codes needed.

**Create:**
- `src/vn_parcel_bot/carrier_catalog.py` (only `CarrierCode` for now), `src/vn_parcel_bot/carriers/__init__.py` (empty for now), `carriers/models.py` (only `ErrorReason` and `CarrierError` for now), `carriers/http.py`, `carriers/common.py`
- `scripts/probe_carriers.py`
- `tests/test_http_client.py`, `tests/test_carrier_common.py`, `tests/test_fixtures.py`
- `tests/fixtures/FIXTURES.md` and the fixtures in step 4

> `common.py` needs `CarrierCode` and `CarrierError`. Create them now exactly as §9.5/§9.6; Prompt 3 completes both files.

**Build:**

1. `carriers/http.py`:
   ```python
   DEFAULT_HEADERS = {
       "User-Agent": (
           "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
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
2. `carriers/common.py` — §9.7:
   - `request`: `response = await http.request(method, url, **kwargs)`; `httpx.TimeoutException` / `httpx.TransportError` → `CarrierError(carrier, "network", type(exc).__name__)`. Status in `not_found_statuses` → return the response. 403/429 → `blocked` (`detail=str(status)`). Any other status outside 200–299 → `http_status` (`detail=str(status)`). A 2xx response whose `content-type` does not contain `json` and whose text `looks_like_challenge` → `blocked` (`"challenge page"`). Otherwise return the response.
   - `json_body`: `response.json()`; `ValueError` → `blocked` (`"html instead of json"`) if `response.text.lstrip().startswith("<")`, else `parse` (`"invalid json"`).
   - `looks_like_challenge`, `clean_text`, `VN_TZ` exactly §9.7.
   - `parse_gmt_offset(value, default)`: `s = str(value).strip().upper()` (return `default` for `None`); regex `^(?:GMT|UTC)?\s*([+-]?)(\d{1,2})(?::?(\d{2}))?$`; hours ≤ 14 and minutes < 60 → `timezone(sign * timedelta(hours=h, minutes=m))`; anything else → `default`.
3. `scripts/probe_carriers.py` (standalone CLI, `asyncio.run`; settings from `.env` via `python-dotenv` + `Settings.from_env(os.environ)`):
   - `python scripts/probe_carriers.py carriers [--file probe_codes.local.txt] [--parse] [--spx-secret SECRET]`
     - File: one parcel per line, `#` comments allowed: `<carrier> <code> [last4] [state-you-believe]`, carrier ∈ `spx jt cainiao fourpx ninjavan ghn best`.
     - Sends the raw request exactly as documented in §5.3–§5.8 through `make_http_client` (SPX unsigned unless `--spx-secret`; GHN hashes the digits per §5.8; BEST: `GET https://www.best-inc.vn/track?bills=<code>` just to save the page).
     - Saves the raw body to `tests/fixtures/_raw/<carrier>_<code[:5]>x<code[-3:]>_<YYYYmmdd-HHMMSS>.<json|html>`.
     - Prints one line per request: carrier, **masked** code, HTTP status, byte count, and a structural hint — JSON: top-level keys and the length of the documented event list; HTML: whether the not-found marker and `result-tracking` are present. Never prints bodies.
     - `--parse` is accepted and ignored until Prompt 10A implements it.
     - Sleeps 3–5 s between requests to the same carrier.
   - `python scripts/probe_carriers.py telegram` — calls `getMe` through `httpx` (respecting `TELEGRAM_PROXY_URL`) and prints `OK @<bot_username>` or the exception class name. Never prints the token or URL.
4. **Synthetic fixtures** — UTF-8, JSON pretty-printed with 2-space indent. Build each from the shapes in §5, use only the fake codes below, Vietnamese descriptions, times in September 2026, events listed **newest first** in the file (parsers must sort), 3–5 events per found fixture.

   | Carrier | Files (code) | Must contain |
   |---|---|---|
   | spx | `in_transit.json` (`SPXVN000000000001`), `delivered.json` (`SPXVN000000000002`), `not_found.json` | §5.3 found shape with `current_status` and `tracking_list`; one message containing a literal `\n` sequence; delivered latest message `Giao hàng thành công`; not_found = the verified unknown-code body |
   | jt | `in_transit.html` (`840000000001`), `delivered.html` (`840000000002`), `not_found.html` | the markup below (one event without `event-location`); delivered latest description `Giao hàng thành công`; not_found = a page containing `Không tìm thấy dữ liệu về vận đơn` and `<div class="empty-vandon"></div>` |
   | cainiao | `in_transit.json` (`LP00000000000001`), `delivered.json` (`LP00000000000002`), `not_found.json` (`LP00000000000000`) | §5.5 shape; items with `time` (ms), `timeStr`, `timeZone` `GMT+8`, `desc`, `standerdDesc`, `actionCode`; one in-transit item **without** `time`; delivered latest `GTMS_SIGNED`; not_found = the verified body |
   | fourpx | `in_transit.json` (`4PX0000000000000001`), `delivered.json` (`4PX0000000000000002`), `not_found.json` (`4PX0000000000000000`) | §5.6 shape; `tkTimezone` values `+08:00` and `GMT+7`; delivered latest `tkCode` `FPX_S_OK`; not_found = the verified body |
   | ninjavan | `in_transit.json` (`SPEVN000000000001`), `delivered.json` (`SPEVN000000000002`), `returned.json` (`SPEVN000000000003`), `not_found.json` | §5.7 shape — in_transit in **snake_case** with ISO times and one `DELIVERY_FAILURE` with `failure_reason.vi`; delivered in **camelCase** with epoch-ms times; returned with granular status `Returned to Sender` and a final `DELIVERY_SUCCESS`; not_found = the verified 404 body |
   | ghn | `in_transit.json` (`GA0000000001`), `delivered.json` (`GA0000000002`), `not_found.json` | §5.8 shape; `action_at` ISO strings with `Z`; one log without `status_name`; delivered `order_info.status` `delivered`; not_found = `{"code": 400, "message": "Thông tin không chính xác", "data": null, "code_message": "PHONE_VERIFY_FAIL"}` |

   J&T synthetic markup (Prompt 10A confirms or replaces it):
   ```html
   <!doctype html>
   <html lang="vi"><body>
   <div class="result-tracking">
     <div class="tracking-bill" data-billcode="840000000001">
       <ul class="tracking-events">
         <li class="tracking-event">
           <span class="event-time">11/09/2026 08:15</span>
           <span class="event-desc">Đơn hàng đang được giao đến bạn</span>
           <span class="event-location">Bưu cục Quận 7</span>
         </li>
         <!-- more events, newest first -->
       </ul>
     </div>
   </div>
   </body></html>
   ```
5. `tests/fixtures/FIXTURES.md` — per carrier: **provenance** (`synthetic 2026-09-13`), the request as in §5, JSON paths or CSS selectors, time format and timezone, served order, not-found appearance, delivered/returned markers; and per fixture file: code, event count, latest description, and the oldest event's local time in Asia/Ho_Chi_Minh as `dd/mm HH:MM`. Later tests assert these facts.

**Tests (write first):**

`tests/test_http_client.py`
- `test_client_defaults(settings)` — `async with make_http_client(settings) as c:` → `c.timeout.connect == settings.http_timeout_seconds`, `c.headers["User-Agent"] == DEFAULT_HEADERS["User-Agent"]`, `c.headers["Accept-Language"]` starts with `vi-VN`, `c.follow_redirects is True`.

`tests/test_carrier_common.py` (`respx.mock`, `async with httpx.AsyncClient() as http:`)
- `test_request_returns_2xx_response`.
- `test_request_maps_blocked_and_http_status` — parametrize `(403, "blocked"), (429, "blocked"), (500, "http_status"), (404, "http_status")`; `err.carrier == "cainiao"`.
- `test_request_not_found_status_passthrough` — 404 with `not_found_statuses=(404,)` returns the response.
- `test_request_network_error` — `side_effect=httpx.ConnectTimeout("t")` → `network`, `detail == "ConnectTimeout"`.
- `test_request_challenge_page_blocked` — 200 `text/html` body `<script>document.cookie="D1N=1";window.location.reload(true);</script>` → `blocked`.
- `test_json_body_html_blocked_and_text_parse` — `"<html>"` → `blocked`; `"oops"` → `parse`.
- `test_looks_like_challenge_cases` — `captcha`, `x5sec`, cookie + reload → True; the J&T in-transit fixture → False.
- `test_parse_gmt_offset_cases` — `"GMT+8"` → +8 h; `"+07:00"` → +7 h; `"UTC-3"` → −3 h; `"+0530"` → +5 h 30; `8` → +8 h; `None`, `"abc"`, `"GMT+99"` → the default.
- `test_clean_text` — `"  a \n b\t"` → `"a b"`.

`tests/test_fixtures.py`
- `test_every_json_fixture_parses` — every `tests/fixtures/*/*.json` loads.
- `test_fixture_set_complete` — every file in step 4 exists.
- `test_fixtures_documented` — every fixture file name appears in `FIXTURES.md`.
- `test_fixture_codes_are_fake` — every match of `SPXVN\d+|SPEVN\d+|LP\d{14}|4PX\d{16}|GA\d{10}|(?<!\d)84\d{10}(?!\d)` in any fixture consists of its prefix, zeros, and one final digit 0–3.

**Verify:**
```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m ruff format --check .
.\.venv\Scripts\python scripts\probe_carriers.py --help
```
Expected: gates green; the help text lists `carriers` and `telegram`.

**Done when:** gates green; every fixture is listed in FIXTURES.md with provenance `synthetic`.

**Commit:** `test: http client, carrier helpers, probe script, synthetic fixtures`

---

## Prompt 3 — Carrier catalog, tracking codes, tracking models

**Goal:** Pure, fully tested building blocks: the carrier catalog (tiers, links, aliases), code normalization and detection, the carrier-neutral tracking data types, and shared test fakes.

**Spec:** §4.4, §5.1, §5.2, §7 (event key), §9.5, §9.6, §13 (fakes).

**Preconditions:** Prompt 2 committed.

**Create/complete:**
- `src/vn_parcel_bot/carrier_catalog.py` (complete), `src/vn_parcel_bot/tracking_codes.py`, `src/vn_parcel_bot/carriers/models.py` (complete)
- `tests/fakes.py`
- `tests/test_carrier_catalog.py`, `tests/test_tracking_codes.py`, `tests/test_models.py`

**Build:**

1. `carrier_catalog.py` — §9.5 with the §5.1 table: display names `SPX`, `J&T`, `Cainiao`, `4PX`, `Ninja Van`, `GHN`, `BEST Express`, `YunExpress`, `GHTK`, `Viettel Post`, `VNPost`, `LEX VN`. `official_url` returns `None` when the template is `None`; replaces `{code}` with `urllib.parse.quote(code, safe="")`; returns templates without `{code}` unchanged. `seventeen_track_url` uses the same quoting. `parse_carrier_alias` per §5.2 (dict lookup after normalization).
2. `tracking_codes.py` — `_RULES: tuple[tuple[re.Pattern[str], tuple[CarrierCode, ...]], ...]` in §5.2 order; `_GENERIC_ONLY_RULE_INDEX = 11`; `_TOKEN = re.compile(r"[0-9A-Za-z][0-9A-Za-z.\-]*[0-9A-Za-z]")`; `_STRIP_CHARS = ",;:()[]<>\"'."`. `normalize_code`: `re.sub(r"[\s\-]", "", raw.upper()).strip(_STRIP_CHARS)`. `extract_codes` per §5.2 (a rule-12 token is kept only if `normalize_code(text) == token`).
3. `carriers/models.py` — §9.6:
   - `TrackingEvent.__post_init__`: `if self.time.tzinfo is None or self.time.utcoffset() is None: raise ValueError("TrackingEvent.time must be timezone-aware")`.
   - `TrackingEvent.key`:
     ```python
     def _norm(s: str) -> str:
         return " ".join(s.split()).casefold()


     @property
     def key(self) -> str:
         utc = self.time.astimezone(UTC).replace(microsecond=0).isoformat()
         raw = f"{utc}|{_norm(self.description)}|{_norm(self.location or '')}"
         return hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
     ```
   - `TrackingResult.__post_init__`: `object.__setattr__(self, "events", tuple(sorted(self.events, key=lambda e: e.time)))` (stable sort).
   - `CarrierError`: stores attributes, `super().__init__(f"{carrier}:{reason}: {detail}")`.
   - `Carrier` is a `typing.Protocol` (not runtime-checkable).
4. `tests/fakes.py`:
   ```python
   class FakeClock:
       def __init__(self, start: datetime) -> None: ...  # must be aware
       def __call__(self) -> datetime: ...  # current time
       def advance(self, delta: timedelta) -> None: ...
       def set(self, value: datetime) -> None: ...


   class FakeCarrier:
       def __init__(
           self, code: CarrierCode, *, needs_phone: bool | None = None, display_name: str | None = None
       ) -> None: ...  # defaults from CATALOG

       results: dict[tuple[str, str | None], TrackingResult | CarrierError]
       calls: list[tuple[str, str | None]]

       async def fetch(
           self, http, tracking_number: str, phone_last4: str | None = None
       ) -> TrackingResult: ...

       # unknown key -> TrackingResult(carrier=code, tracking_number=..., found=False)


   class FakeNotifier:
       def __init__(self, fail_with: Exception | None = None) -> None: ...

       sent: list[tuple[int, str, bool]]

       async def send(
           self, chat_id: int, text: str, *, silent: bool = False
       ) -> None: ...  # records then raises fail_with if set


   def ev(
       minutes: int,
       description: str = "Đang vận chuyển",
       location: str | None = "Kho HCM",
       base: datetime = datetime(2026, 9, 1, 8, 0, tzinfo=UTC),
   ) -> TrackingEvent: ...


   def found(
       code: CarrierCode,
       tracking_number: str,
       *events: TrackingEvent,
       delivered: bool = False,
       returned: bool = False,
   ) -> TrackingResult: ...
   ```

**Tests (write first):**

`tests/test_carrier_catalog.py`
- `test_catalog_has_twelve_carriers_in_table_order`.
- `test_tracked_tuple` — `TRACKED == ("spx", "jt", "cainiao", "fourpx", "ninjavan", "ghn")` and equals the codes with `tracked=True`.
- `test_needs_phone_only_jt_and_ghn`.
- `test_link_only_carriers_have_templates_tracked_have_none`.
- `test_official_url_quotes_code` — `official_url("ghtk", "S123.AB") == "https://i.ghtk.vn/S123.AB"`; `official_url("yunexpress", "YT1#2")` contains `YT1%232`.
- `test_official_url_without_placeholder` — `viettelpost` returns its template unchanged.
- `test_official_url_tracked_is_none` — `spx` → `None`.
- `test_seventeen_track_url` — `"EB123456789VN"` → `https://t.17track.net/vi#nums=EB123456789VN`.
- `test_parse_carrier_alias_variants` — parametrize `("J&T", "jt"), ("jnt", "jt"), ("4PX", "fourpx"), ("Ninja-Van", "ninjavan"), ("EMS", "vnpost"), ("lazada", "lex"), ("Viettel Post", "viettelpost"), ("abc", None), ("", None)`.

`tests/test_tracking_codes.py`
- `test_normalize_strips_spaces_dashes_case` — `" spxvn 0533-8454 932c "` → `"SPXVN05338454932C"`.
- `test_normalize_strips_surrounding_punctuation` — `"(841000072647),"` → `"841000072647"`.
- `test_normalize_keeps_internal_dots` — `"s1234567.mb12.d5.123456789."` → `"S1234567.MB12.D5.123456789"`.
- `test_detect_each_rule` — parametrize: `SPXVN05338454932C` → `["spx"]`; `SPEVN000000000001` → `["ninjavan"]`; `LP00123456789012` → `["cainiao"]`; `LX123456789CN` → `["cainiao"]`; `4PX3000123456789CN` → `["fourpx"]`; `YT1234567890123456` → `["yunexpress"]`; `EB123456789VN` → `["vnpost"]`; `LEXVN00123456` → `["lex"]`; `S1234567.MB12.D5.123456789` → `["ghtk"]`; `841000072647` → `["jt", "best", "viettelpost"]`; `8410000726470` → `["best"]`; `GAN6DKKU12` → `["ghn", "ninjavan"]`.
- `test_detect_first_rule_wins` — `SPXVN05338454932C` does not include `ghn`.
- `test_detect_no_match` — `""`, `"AB12"`, `"ABCDEFGH"`, `"12345678"`, `"71426082060"`, `"GAN6DKKU12345678"` → `[]`.
- `test_generic_code_re` — `"AB12C"` no (5 chars), `"AB1234"` yes, `"A.B"` no.
- `test_extract_codes_mixed_text_in_order` — `"Mã: spxvn05338454932c và J&T 841000072647."` → `["SPXVN05338454932C", "841000072647"]`.
- `test_extract_codes_dedupes`.
- `test_extract_codes_ignores_longer_digit_runs` — `"84100007264701"` → `[]`.
- `test_extract_codes_generic_only_when_alone` — `"GAN6DKKU12"` → `["GAN6DKKU12"]`; `" gan6dkku12 "` → `["GAN6DKKU12"]`; `"đơn GAN6DKKU12 nhé"` → `[]`; `"IPHONE15PROMAX 841000072647"` → `["841000072647"]`.
- `test_extract_codes_none` — `"xin chào"` → `[]`.
- `test_extract_codes_dashed_code_in_text` — `"mã SPXVN-0533-8454-932C nhé"` → `["SPXVN05338454932C"]`.
- `test_is_valid_last4` — `"1234"` True; `"123"`, `"12345"`, `"12a4"`, `" 1234"` False.
- `test_mask_code` — `"SPXVN05338454932C"` → `"SPXVN…32C"`.

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

**Commit:** `feat: carrier catalog, code detection, tracking models, test fakes`

---

## Prompt 4 — SPX carrier

**Goal:** `SpxCarrier.fetch`, `sign_spx_code` and `parse_spx_response` for SPX Express Vietnam, with all error paths mapped.

**Spec:** §5.3, §5.9, §9.7; `tests/fixtures/FIXTURES.md` (SPX section) for fixture facts.

**Preconditions:** Prompt 3 committed.

**Create:** `src/vn_parcel_bot/carriers/spx.py`, `tests/test_spx.py`

**Build:**

1. Constants exactly §9.7.
2. `sign_spx_code(code, timestamp, secret)` → `f"{code}|{timestamp}{hashlib.sha256(f'{code}{timestamp}{secret}'.encode()).hexdigest()}"`.
3. `parse_spx_response(payload, tracking_number)`:
   - Not a dict, or no `retcode` → `CarrierError("spx", "parse", "unexpected payload")`.
   - `retcode != 0` → `CarrierError("spx", "parse", f"retcode={retcode}")`.
   - `data` not a dict or empty, or `tracking_list` missing/empty → `TrackingResult(carrier="spx", tracking_number=tracking_number, found=False)`.
   - `tracking_list` not a list, an item not a dict, `timestamp` not an `int` (bools rejected), or `message` not a non-blank `str` → `parse` error.
   - Events per §5.3; `delivered` / `returned` per §5.3 using `clean_text(current_status)` and the latest description.
4. `SpxCarrier.__init__(*, secret=SPX_SIGNING_SECRET, clock=time.time)`; `fetch(http, tracking_number, phone_last4=None)`:
   - `value = tracking_number if secret is None else sign_spx_code(tracking_number, int(clock()), secret)`.
   - `response = await request(http, "spx", "GET", SPX_TRACKING_URL, params={"sls_tracking_number": value})`.
   - `return parse_spx_response(json_body("spx", response), tracking_number)`.

**Tests (write first)** — helper `load_json(name)` reads `tests/fixtures/spx/<name>.json`; replace `N`, `TEXT`, `TIME` with the facts in FIXTURES.md:
- `test_parse_in_transit` — `found`, `len(events) == N`, ascending, all times aware UTC, `latest.description == "TEXT"`, not delivered, not returned.
- `test_parse_delivered` — `delivered is True`, `returned is False`.
- `test_parse_returned_marker` — in-transit payload with `current_status = "Hoàn hàng thành công"` → `returned is True`.
- `test_parse_not_found` — `found is False`, `events == ()`.
- `test_parse_oldest_event_local_time` — `events[0].time.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%d/%m %H:%M") == "TIME"`.
- `test_parse_replaces_literal_newline_sequences` — message `"Đơn hàng\\nđã đến kho"` → `"Đơn hàng đã đến kho"`.
- `test_parse_rejects_non_dict` — `[]` → `parse`.
- `test_parse_unknown_retcode` — `{"retcode": 99999, "message": "x", "data": {}}` → `parse`.
- `test_parse_rejects_malformed_list` — `tracking_list = "x"` → `parse`.
- `test_parse_rejects_item_without_timestamp`.
- `test_sign_spx_code_vector` — equals the f-string computed with `hashlib` in the test for `("SPXVN000000000001", 1757000000, "s3cr3t")`; starts with `"SPXVN000000000001|1757000000"`; total length = len(code) + 1 + 10 + 64.
- `test_fetch_unsigned_sends_plain_code` (`respx.mock`) — `request.url.params["sls_tracking_number"] == "SPXVN000000000001"`; in-transit fixture → `found`.
- `test_fetch_signed_uses_clock` — `SpxCarrier(secret="s", clock=lambda: 1757000000.9)` sends `sign_spx_code(code, 1757000000, "s")`.
- `test_fetch_maps_errors` — parametrize 403 → `blocked`, 500 → `http_status`, `httpx.ConnectTimeout` → `network`, 200 `"<html>captcha</html>"` → `blocked`.
- `test_carrier_attributes` — `code == "spx"`, `display_name == "SPX"`, `needs_phone is False`.

**Verify:** quality gates.

**Done when:** gates green; `pytest --cov=vn_parcel_bot.carriers.spx` ≥ 90 %.

**Commit:** `feat: SPX Express Vietnam carrier`

---

## Prompt 5 — J&T carrier

**Goal:** `JtCarrier.fetch` and `parse_jt_html` for J&T Express Vietnam HTML.

**Spec:** §5.4, §5.9, §9.7; `tests/fixtures/FIXTURES.md` (J&T section) for the request, selectors, time format and markers.

**Preconditions:** Prompt 4 committed.

**Create:** `src/vn_parcel_bot/carriers/jt.py`, `tests/test_jt.py`

**Build:**

1. Constants: `JT_TRACKING_URL`, `NOT_FOUND_MARKER = "Không tìm thấy dữ liệu"`, `DELIVERED_MARKERS = ("giao hàng thành công", "đã ký nhận")`, `RETURNED_MARKERS = ("hoàn hàng thành công", "đã hoàn hàng", "đã trả hàng cho người gửi")`, and selectors from FIXTURES.md: `RESULT_SELECTOR = ".result-tracking"`, `BILL_SELECTOR = "[data-billcode]"`, `EVENT_SELECTOR = ".tracking-event"`, `TIME_SELECTOR = ".event-time"`, `DESCRIPTION_SELECTOR = ".event-desc"`, `LOCATION_SELECTOR = ".event-location"`, `TIME_FORMATS = ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M")`.
2. `parse_jt_html(html, tracking_number)` using `BeautifulSoup(html, "html.parser")`:
   - Decide in this order:
     1. Events found with `EVENT_SELECTOR` inside the result container (inside the bill block whose `data-billcode` equals `tracking_number` when bill blocks exist) → **found**.
     2. Else `NOT_FOUND_MARKER` in the page text, or an `.empty-vandon` element present → **not found**.
     3. Else → `CarrierError("jt", "parse", "no result or not-found marker")`.
   - An event missing time or description → `parse` error; unparseable time → `parse` error.
   - Times: first matching `TIME_FORMATS` → `.replace(tzinfo=VN_TZ)`.
   - Text: `clean_text(el.get_text(" "))`; empty location → `None`.
   - `delivered` = latest description matches `DELIVERED_MARKERS` (casefold substring); `returned` = any description matches `RETURNED_MARKERS` and not delivered.
3. `JtCarrier.fetch(http, tracking_number, phone_last4)`:
   - `phone_last4 is None` → `raise ValueError("J&T requires phone_last4")`.
   - `response = await request(http, "jt", "GET", JT_TRACKING_URL, params={"type": "track", "billcode": tracking_number, "cellphone": phone_last4})`.
   - `return parse_jt_html(response.text, tracking_number)`.

**Tests (write first)** — helper `load_html(name)` reads `tests/fixtures/jt/<name>.html`; replace `N`/`TEXT`/`TIME` with fixture facts:
- `test_parse_in_transit` — `found`, `len(events) == N`, ascending, aware times, `latest.description == "TEXT"`, not delivered; the event without location has `location is None`.
- `test_parse_delivered` — `delivered is True`.
- `test_parse_returned_marker` — in-transit HTML with the newest description replaced by `Hoàn hàng thành công` → `returned is True`.
- `test_parse_not_found_fixture` — `found is False`.
- `test_parse_not_found_marker_minimal` — `"<html><body><p>Không tìm thấy dữ liệu về vận đơn</p></body></html>"` → `found is False`.
- `test_parse_empty_vandon_minimal` — `'<div class="empty-vandon"></div>'` → `found is False`.
- `test_parse_unknown_page_raises` — `"<html><body>Bảo trì hệ thống</body></html>"` → `parse`.
- `test_parse_event_missing_time_raises` — in-transit fixture with the first time element removed → `parse`.
- `test_parse_picks_matching_bill_block` — two bill blocks with different `data-billcode` → only events of the requested code.
- `test_parse_oldest_event_local_time` — equals FIXTURES.md.
- `test_fetch_requires_phone` — `ValueError`.
- `test_fetch_sends_code_and_digits` (`respx`) — params `billcode=840000000001`, `cellphone=1234`, `type=track`; in-transit fixture → `found`.
- `test_fetch_maps_http_errors` — `403/429 → blocked`, `500/404 → http_status`.
- `test_fetch_network_error` — `httpx.ReadTimeout` → `network`.
- `test_fetch_challenge_page_blocked` — 200 with `"<html>captcha</html>"` → `blocked`.
- `test_carrier_attributes` — `code == "jt"`, `display_name == "J&T"`, `needs_phone is True`.

**Verify:** quality gates.

**Done when:** gates green; `pytest --cov=vn_parcel_bot.carriers.jt` ≥ 90 %.

**Commit:** `feat: J&T Express Vietnam carrier`

---

## Prompt 5A — Cainiao and 4PX carriers

**Goal:** Cross-border carriers Cainiao and 4PX, parsed from their JSON APIs.

**Spec:** §5.5, §5.6, §5.9, §9.7; FIXTURES.md (Cainiao and 4PX sections).

**Preconditions:** Prompt 5 committed.

**Create:** `src/vn_parcel_bot/carriers/cainiao.py`, `carriers/fourpx.py`, `tests/test_cainiao.py`, `tests/test_fourpx.py`

**Build:**

1. `cainiao.py` — §5.5 and §9.7:
   - `parse_cainiao_response(payload, tracking_number)`: rules in §5.5. Time helper: `int` `time` (not bool) → UTC from ms; else `datetime.strptime(timeStr, "%Y-%m-%d %H:%M:%S").replace(tzinfo=parse_gmt_offset(timeZone, timezone(timedelta(hours=8))))`; neither → `parse`. `delivered` = latest `actionCode` in `DELIVERED_ACTION_CODES`; `returned` = not delivered and `"RETURN" in latest actionCode`.
   - `CainiaoCarrier.fetch`: `request(http, "cainiao", "GET", CAINIAO_TRACKING_URL, params={"mailNos": tracking_number, "lang": "en-US", "language": "en-US"})` → `json_body` → parse. `phone_last4` ignored.
2. `fourpx.py` — §5.6 and §9.7:
   - `parse_fourpx_response(payload, tracking_number)`: rules in §5.6; time = `datetime.strptime(tkDateStr, "%Y-%m-%d %H:%M:%S").replace(tzinfo=parse_gmt_offset(tkTimezone, timezone(timedelta(hours=8))))`; `delivered` = latest `tkCode` starts with `DELIVERED_CODE_PREFIX`; `returned` always False.
   - `FourPxCarrier.fetch`: `request(http, "fourpx", "POST", FOURPX_TRACKING_URL, json={"queryCodes": [tracking_number], "language": "en-us", "translateLanguage": "en-us"})` → `json_body` → parse.

**Tests (write first):**

`tests/test_cainiao.py`
- `test_parse_in_transit` — N events ascending, latest TEXT, not delivered.
- `test_parse_item_without_time_uses_timestr_and_zone` — that event's UTC time equals `timeStr` minus 8 h.
- `test_parse_delivered` — `GTMS_SIGNED` → delivered.
- `test_parse_returned_action_code` — latest `actionCode` `"GTMS_RETURN_SIGNED"` in a modified payload → returned, not delivered.
- `test_parse_not_found_verified_body`.
- `test_parse_success_false_raises`, `test_parse_empty_module_raises`, `test_parse_item_without_description_raises`, `test_parse_item_without_any_time_raises`.
- `test_parse_description_falls_back_to_standerd_desc`.
- `test_fetch_sends_params` (`respx`) — `mailNos`, `lang=en-US`, `language=en-US`.
- `test_fetch_maps_errors` — 403 → blocked; 200 HTML → blocked; `ConnectTimeout` → network.
- `test_carrier_attributes`.

`tests/test_fourpx.py`
- `test_parse_in_transit` — N events ascending; the `+08:00` and `GMT+7` events convert to the UTC times written in FIXTURES.md.
- `test_parse_delivered` — `FPX_S_OK` → delivered.
- `test_parse_not_found_null_tracks` and `test_parse_not_found_empty_tracks`.
- `test_parse_result_not_one_raises`, `test_parse_missing_datestr_raises`.
- `test_parse_uses_translated_desc_when_desc_blank`.
- `test_parse_bad_timezone_defaults_to_plus_eight`.
- `test_parse_location_blank_is_none`.
- `test_fetch_posts_json_body` (`respx`) — `json.loads(request.content) == {"queryCodes": ["4PX0000000000000001"], "language": "en-us", "translateLanguage": "en-us"}`.
- `test_fetch_maps_errors`, `test_carrier_attributes`.

**Verify:** quality gates.

**Done when:** gates green; coverage of both modules ≥ 90 %.

**Commit:** `feat: Cainiao and 4PX carriers`

---

## Prompt 5B — Ninja Van and GHN carriers, carrier registry

**Goal:** Ninja Van and GHN carriers, then the `CARRIERS` registry of all tracked carriers.

**Spec:** §5.7, §5.8, §5.9, §9.7; FIXTURES.md (Ninja Van and GHN sections).

**Preconditions:** Prompt 5A committed.

**Create/modify:** create `src/vn_parcel_bot/carriers/ninjavan.py`, `carriers/ghn.py`, `tests/test_ninjavan.py`, `tests/test_ghn.py`, `tests/test_carrier_registry.py`; replace `src/vn_parcel_bot/carriers/__init__.py`.

**Build:**

1. `ninjavan.py` — §5.7 and §9.7:
   - Key helper `_get(d, snake, camel)` returning the first present key.
   - `parse_ninjavan_response(payload, tracking_number)`: not a dict → `parse`; if `events` is absent and `payload.get("data")` is a dict → use `payload["data"]`; `events` not a list → `parse`; empty → not found. Each event: `type` required (str); time: `int` → UTC from ms, `str` → `datetime.fromisoformat` (naive → `VN_TZ`), else `parse`; description = `NINJAVAN_EVENT_TEXT.get(type)` or `type.replace("_", " ").capitalize()`, plus `" – " + reason` for `DELIVERY_FAILURE` when `failure_reason`/`failureReason` has `vi` or `en`; location = `hub_name`/`hubName` from the event's `data` or `None`. `returned` = granular status casefold equals `RETURNED_GRANULAR_STATUS`; `delivered` = not returned and latest `type` in `DELIVERED_TYPES`.
   - `NinjaVanCarrier.fetch`: `response = await request(http, "ninjavan", "GET", NINJAVAN_TRACKING_URL, params={"tracking_id": tracking_number}, not_found_statuses=(404,))`; `payload = json_body(...)`; on 404: `payload["error"]["code"] == NOT_FOUND_ERROR_CODE` → not found, else `CarrierError("ninjavan", "http_status", "404")`; otherwise parse.
2. `ghn.py` — §5.8 and §9.7:
   - `ghn_phone_verify(code, last4)` → `hashlib.sha256(f"{code}|{last4}".encode("utf-8")).hexdigest()`.
   - `parse_ghn_response(payload, tracking_number)`: not a dict → `parse`; `code == 400` → not found; `code != 200` → `CarrierError("ghn", "http_status", f"code={code}")`; `data` not a dict → `parse`; `tracking_logs` missing/empty → not found; not a list → `parse`. Event per §5.8 (`action_at` required str; `Z` → `+00:00`). `delivered` / `returned` per §5.8 using `order_info.status` and the latest log status.
   - `GhnCarrier.fetch(http, tracking_number, phone_last4)`: `None` → `ValueError`; `response = await request(http, "ghn", "POST", GHN_TRACKING_URL, json={"order_code": tracking_number, "phone_verify": ghn_phone_verify(tracking_number, phone_last4)}, not_found_statuses=(400,))`; `payload = json_body(...)`; a 400 whose payload is not a dict → `CarrierError("ghn", "http_status", "400")`; else parse.
3. `carriers/__init__.py`:
   ```python
   CARRIERS: dict[CarrierCode, Carrier] = {
       "spx": SpxCarrier(),
       "jt": JtCarrier(),
       "cainiao": CainiaoCarrier(),
       "fourpx": FourPxCarrier(),
       "ninjavan": NinjaVanCarrier(),
       "ghn": GhnCarrier(),
   }


   def get_carrier(code: CarrierCode) -> Carrier:
       return CARRIERS[code]
   ```

**Tests (write first):**

`tests/test_ninjavan.py`
- `test_parse_in_transit_snake_case` — N events ascending; the failure event text contains the Vietnamese reason; hub events carry the hub name as location.
- `test_parse_delivered_camel_case_epoch_ms` — delivered.
- `test_parse_returned_granular_status` — returned True, delivered False.
- `test_parse_unknown_type_capitalized` — `"SOME_NEW_TYPE"` → `"Some new type"`.
- `test_parse_empty_events_not_found`; `test_parse_missing_events_raises`; `test_parse_data_wrapper_unwrapped`; `test_parse_event_without_time_raises`.
- `test_fetch_404_not_found_code` (`respx`) — verified body → `found is False`.
- `test_fetch_404_other_error_http_status`.
- `test_fetch_sends_tracking_id_param`; `test_fetch_maps_errors` (403, `ConnectTimeout`); `test_carrier_attributes`.

`tests/test_ghn.py`
- `test_phone_verify_vector` — equals `hashlib.sha256(b"GA0000000001|1234").hexdigest()`.
- `test_parse_in_transit` — N logs ascending; the log without `status_name` uses `GHN_STATUS_TEXT`.
- `test_parse_delivered`; `test_parse_returned_order_status` (modified payload `order_info.status = "returned"`).
- `test_parse_unknown_status_uses_raw_code`.
- `test_parse_code_400_not_found`; `test_parse_code_500_http_status`; `test_parse_empty_logs_not_found`; `test_parse_non_dict_raises`.
- `test_fetch_posts_code_and_hash` (`respx`) — body has `order_code` and `phone_verify == ghn_phone_verify(code, "1234")`.
- `test_fetch_400_phone_verify_fail_is_not_found` — HTTP 400 with the not_found fixture → `found is False`.
- `test_fetch_400_non_json_http_status`.
- `test_fetch_requires_phone`; `test_fetch_maps_errors` (403 → blocked); `test_carrier_attributes`.

`tests/test_carrier_registry.py`
- `test_registry_keys_equal_tracked_in_order` — `tuple(CARRIERS) == TRACKED`.
- `test_registry_attributes_match_catalog` — `.code == key`, `.needs_phone == CATALOG[key].needs_phone`, `.display_name == CATALOG[key].display_name`.
- `test_get_carrier`.

**Verify:** quality gates.

**Done when:** gates green; `pytest --cov=vn_parcel_bot.carriers` ≥ 90 %.

**Commit:** `feat: Ninja Van and GHN carriers, carrier registry`

---

## Prompt 6 — Database schema and repository

**Goal:** A migrated SQLite database and an async `Repository` that is the only code touching SQL, including unresolved parcels.

**Spec:** §7 (SQL verbatim), §9.8.

**Preconditions:** Prompt 5B committed.

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
   (`executescript` commits implicitly; that is fine for v1. Add `# noqa: S608` only if ruff flags the f-string.)
2. `repo.py`:
   - `Repository.open(db_path)`: `Path(db_path).parent.mkdir(parents=True, exist_ok=True)`; `conn = await aiosqlite.connect(db_path)`; `conn.row_factory = aiosqlite.Row`; `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`, `PRAGMA busy_timeout=5000`; `await migrate(conn)`.
   - Private helpers: `_to_db(dt: datetime) -> str` (`dt.astimezone(UTC).isoformat(timespec="seconds")`; `ValueError` for naive), `_from_db(s: str | None) -> datetime | None` (`datetime.fromisoformat`), `_candidates_to_db(codes) -> str` (`",".join`), `_candidates_from_db(s) -> tuple[CarrierCode, ...]`.
   - Row → `User` / `Parcel` mappers (`bool(row["is_admin"])`, candidates split, etc.). `Parcel.is_resolved` = `carrier is not None`; `try_order()` = `(carrier,)` if resolved else `candidates`.
   - `upsert_user`: `INSERT … ON CONFLICT(telegram_id) DO UPDATE SET` only the fields that are not `None`; `created_at` set on insert only; new users default `is_allowed=0, is_admin=0`.
   - `add_parcel`: validate (`ValueError` if `candidates` is empty, or `carrier is not None and tuple(candidates) != (carrier,)`); insert with `state='pending'`, `created_at=updated_at=now`; `sqlite3.IntegrityError` whose message contains `UNIQUE` → `DuplicateParcelError`; return `get_parcel(lastrowid)`.
   - `find_parcel(user_id, tracking_number)`: by the unique pair.
   - `list_parcels(user_id, *, terminal_since)`: `WHERE user_id=? AND (state IN ('pending','in_transit') OR updated_at >= ?) ORDER BY created_at, id`.
   - `due_parcels(now)`: `JOIN users u ON u.telegram_id = p.user_id WHERE u.is_allowed = 1 AND p.state IN ('pending','in_transit') AND p.next_check_at <= ? ORDER BY p.next_check_at, p.id`.
   - `resolve_carrier(parcel_id, carrier, now)`: `UPDATE parcels SET carrier=?, candidates=?, updated_at=? WHERE id=?`.
   - `record_check_success`: `SET state=?, last_status_text=COALESCE(?, last_status_text), last_event_at=COALESCE(?, last_event_at), delivered_at=COALESCE(?, delivered_at), consecutive_failures=0, next_check_at=?, updated_at=?`.
   - `record_check_failure`: `UPDATE … SET consecutive_failures = consecutive_failures + 1, next_check_at=?, updated_at=? … RETURNING consecutive_failures`.
   - `insert_events`: for each event in ascending order `INSERT OR IGNORE INTO events (...)`; `cursor.rowcount == 1` → new; commit once; return new events ascending.
   - `list_events(parcel_id, limit)`: `SELECT … ORDER BY event_time DESC, id DESC LIMIT ?`, reversed to ascending; rebuild `TrackingEvent`.
   - `delete_terminal_before(cutoff)`: `DELETE FROM parcels WHERE state IN (<terminal>) AND updated_at < ?`; return `rowcount`.
   - Every write method commits.

**Tests (write first)** — fixture `repo`: `r = await Repository.open(tmp_path / "t.sqlite3")`, yield, `await r.close()`. `T0 = datetime(2026, 9, 1, 1, 0, tzinfo=UTC)`, `ev()` from `tests/fakes.py`. Helper `add(repo, user_id=1, code="SPXVN000000000001", carrier="spx", candidates=None, **kw)` defaults `candidates` to `(carrier,)`.

- `test_migrate_sets_user_version_and_is_idempotent` — open, close, reopen → `PRAGMA user_version == 1`, no error.
- `test_foreign_keys_enabled`.
- `test_upsert_user_insert_then_partial_update` — insert with `name="A"`; update with `is_allowed=True` only → name still `"A"`, allowed `True`, `created_at` unchanged.
- `test_set_default_phone_and_clear`.
- `test_default_phone_check_constraint` — raw `UPDATE users SET default_phone_last4='12a4'` raises `sqlite3.IntegrityError`.
- `test_add_parcel_and_get` — fields round-trip; `state == "pending"`; datetimes aware UTC; `candidates == ("spx",)`; `is_resolved`.
- `test_add_unresolved_parcel` — `carrier=None, candidates=("ghn", "ninjavan")` → `is_resolved is False`, `try_order() == ("ghn", "ninjavan")`.
- `test_add_parcel_validates_candidates` — empty candidates → `ValueError`; `carrier="spx", candidates=("spx", "jt")` → `ValueError`.
- `test_unresolved_cannot_be_in_transit` — raw `UPDATE parcels SET state='in_transit'` on an unresolved parcel raises `sqlite3.IntegrityError`.
- `test_carrier_check_constraint` — raw `UPDATE parcels SET carrier='dhl'` raises.
- `test_add_parcel_duplicate_raises_even_with_other_carrier` — same user and code, `carrier="jt"` second time → `DuplicateParcelError`.
- `test_same_code_different_users_allowed`.
- `test_resolve_carrier` — unresolved → `carrier == "ninjavan"`, `candidates == ("ninjavan",)`, `updated_at` advanced.
- `test_list_parcels_includes_recent_terminal_only` — active A, delivered B (updated 1 day ago), delivered C (updated 5 days ago), `terminal_since = now - 3 days` → `[A, B]`.
- `test_count_active_parcels`.
- `test_due_parcels_filters_state_time_and_allowed` — due active of allowed user ✔; future `next_check_at` ✘; delivered ✘; due active of not-allowed user ✘; ordering by `next_check_at`.
- `test_insert_events_returns_only_new_ascending` — insert `[e2, e1]` → `[e1, e2]`; insert `[e1, e2, e3]` → `[e3]`; again → `[]`.
- `test_list_events_limit_returns_most_recent_ascending` — 5 events, `limit=3` → last three, ascending.
- `test_delete_parcel_cascades_events`.
- `test_record_check_success_resets_failures_and_keeps_nulls`.
- `test_record_check_failure_increments_and_returns` — returns 1 then 2; `next_check_at` stored.
- `test_set_label_and_clear`.
- `test_delete_terminal_before` — only terminal parcels older than cutoff removed; returns count.
- `test_meta_roundtrip_and_overwrite`.
- `test_naive_datetime_rejected` — `add_parcel(now=datetime(2026, 9, 1), …)` → `ValueError`.

**Verify:** quality gates.

**Done when:** gates green; `pytest --cov=vn_parcel_bot.db` ≥ 90 %.

**Commit:** `feat: SQLite schema and async repository`

---

## Prompt 7 — Texts and message formatting

**Goal:** Every user-visible string in one module and pure formatting functions that build HTML-safe messages, including carrier labels and link lists.

**Spec:** §4, §6.5, §9.9, §17 (copy verbatim).

**Preconditions:** Prompt 6 committed.

**Create:** `src/vn_parcel_bot/texts.py`, `src/vn_parcel_bot/services/__init__.py` (empty), `services/formatting.py`, `tests/test_texts.py`, `tests/test_formatting.py`

> `format_add_outcome` needs `AddOutcome` from Prompt 8. To keep this prompt self-contained, **create `services/parcels.py` now containing only** `AddKind` and the `AddOutcome` dataclass exactly as §9.10. Prompt 8 adds `ParcelService` to the same file.

**Build:**

1. `texts.py` — §17 verbatim (UTF-8 file).
2. `formatting.py` rules:
   - Escape every dynamic value with `html.escape(value, quote=False)`: labels, codes, descriptions, locations, names, error details, refs. URLs use `html.escape(url, quote=True)`.
   - `parcel_title(p)` → escaped label if set, else escaped tracking number.
   - `carrier_name(code)` → `CARRIER_NAMES[code]`; `carrier_names(codes)` → names joined by `CARRIER_SEPARATOR`.
   - `parcel_carrier_label(p)` → `carrier_name(p.carrier)` when resolved, else `carrier_names(p.candidates)`.
   - `format_time(dt, tz)` → `dt.astimezone(tz).strftime(TIME_FORMAT)`.
   - `format_links(code, carriers)` — §4.4.
   - `format_link_only(code, carriers)` → `LINK_ONLY.format(code=escaped, carriers=carrier_names(carriers), links=format_links(code, carriers))`.
   - `format_event_update`: `UPDATE_HEADER` (carrier = `carrier_name(resolved_carrier)` if given, else `parcel_carrier_label`), then `UPDATE_RESOLVED` when `resolved_carrier` is given, then — if `len(new_events) > MAX_EVENTS_IN_UPDATE` — `UPDATE_MORE.format(count=len(new_events) - MAX_EVENTS_IN_UPDATE)`, then one `UPDATE_LINE` (+ `UPDATE_LOCATION` if location) per event for the last `MAX_EVENTS_IN_UPDATE` events in chronological order; then a blank line and `UPDATE_DELIVERED` if `delivered`, else `UPDATE_RETURNED` if `returned`. Result passes through `truncate_message`.
   - `format_parcel_list`: empty → `LIST_EMPTY`; else `LIST_HEADER` + blank line + items joined by `"\n"`. `carrier` = `carrier_name` when resolved else `CARRIER_UNRESOLVED`; `status` = escaped `last_status_text` or `STATE_TEXT[state]`; `time_suffix` = `LIST_TIME_SUFFIX.format(time=…)` when `last_event_at` else `""`; index starts at 1.
   - `format_history`: `HISTORY_HEADER` (carrier = `parcel_carrier_label`) then events **newest first** (at most `MAX_EVENTS_IN_HISTORY`) as `UPDATE_LINE`(+location), or `HISTORY_EMPTY`.
   - `format_add_outcome(outcome, tz, *, max_parcels)`:
     - `added` + `result.found` + `parcel.state == "delivered"` → `ADDED_DELIVERED` (time = latest event).
     - `added` + `result.found` → `ADDED_FOUND` (status = escaped latest description, time = latest event).
     - `added` + `error` → `ADDED_ERROR` (carrier = `parcel_carrier_label`), plus `LINK_EXTRA` when `link_carriers`.
     - `added` + not found → `ADDED_PENDING` (resolved, carrier = `carrier_name`) or `ADDED_PENDING_AUTO` (unresolved, carriers = `carrier_names(parcel.candidates)`); append `ADDED_PENDING_PHONE_HINT` if any of `parcel.candidates` needs a phone; append `LINK_EXTRA.format(carriers=…, links=format_links(code, link_carriers))` when `link_carriers`.
     - `needs_phone` → `ASK_PHONE` (carriers = `carrier_names(outcome.candidates)`); `link_only` → `format_link_only(code, link_carriers)`; `duplicate` → `DUPLICATE`; `limit` → `LIMIT_REACHED`; `invalid_code` → `UNKNOWN_CODE`; `invalid_phone` → `INVALID_PHONE`.
   - `format_needs_phone_multi(codes)` → codes as `<code>…</code>` lines.
   - `format_expired(p)` → `EXPIRED`; `format_stale(p)` → `STALE`.
   - `format_carrier_alert(carrier, count, detail)` → `ALERT_CARRIER` with carrier name and detail escaped and cut to 200 chars.
   - `format_users(users, active_counts, admin_id)` → `USERS_HEADER` + one `USERS_ITEM` per user; role: admin id → `ROLE_ADMIN`, allowed → `ROLE_MEMBER`, else `ROLE_BLOCKED`; name escaped or `"—"`.
   - `format_health(last_poll_at, report, active, users, tz)` → `HEALTH`; `last_poll` = `format_time` or `HEALTH_NEVER`; `fetches`/`new_events` from report or `0`; `failures` = `"spx=2, ghn=1"` style or `"0"`.
   - `truncate_message(text, limit)` → unchanged if `len <= limit`; else cut to the last `"\n"` before `limit - 1` (or hard cut if none) and append `"…"`; result length ≤ limit.

**Tests (write first)** — build `Parcel` objects with a helper `make_parcel(**overrides)`; `TZ = ZoneInfo("Asia/Ho_Chi_Minh")`.

`tests/test_texts.py`
- `test_all_texts_are_html_safe` — for every `str` constant in `texts`, after removing the allowed markup (`<b>`, `</b>`, `<code>`, `</code>`, `<a href="{url}">`, `</a>`) there is no raw `<` or `>`, and every `&` starts an entity (`&amp;`, `&lt;`, `&gt;`).
- `test_placeholders_format_without_error` — each template formats with dummy kwargs for its placeholders (`string.Formatter().parse`).
- `test_state_maps_cover_all_states`.
- `test_carrier_names_cover_catalog` — keys equal `CATALOG` keys.

`tests/test_formatting.py`
- `test_title_prefers_escaped_label` — `"<Áo & quần>"` → `"&lt;Áo &amp; quần&gt;"`; no label → tracking number.
- `test_carrier_labels` — resolved `jt` → `J&amp;T`; unresolved `("ghn", "ninjavan")` → `GHN / Ninja Van`.
- `test_format_time_local` — `01:30Z` → `"01/09 08:30"`.
- `test_format_links_official_then_17track` — `("EB123456789VN", ["vnpost"])` → two lines; first href contains `code=EB123456789VN`, second is the 17TRACK URL; `&` in the VNPost template appears as `&amp;` inside `href`.
- `test_format_links_template_without_code` — `viettelpost` link is the plain template.
- `test_format_link_only` — contains `LINK_ONLY` phrase, carrier names and both links.
- `test_event_update_lines_and_location`; `test_event_update_escapes_description`; `test_event_update_more_than_ten`; `test_event_update_delivered_footer`.
- `test_event_update_resolved_note` — `resolved_carrier="ninjavan"` on an unresolved parcel → header names Ninja Van and contains the `UPDATE_RESOLVED` phrase.
- `test_parcel_list_empty` / `test_parcel_list_items` — numbering, emoji, `STATE_TEXT` fallback, time suffix, `CARRIER_UNRESOLVED` for unresolved.
- `test_history_newest_first_and_empty`.
- `test_add_outcome_each_kind` — parametrized over all kinds and the `added` variants (found, delivered, error, pending resolved, pending unresolved), asserting each template's distinguishing phrase; phone hint only when a candidate needs a phone; `LINK_EXTRA` only with `link_carriers`.
- `test_users_roles`; `test_health_never_and_with_report`; `test_truncate_message`.

**Verify:** quality gates.

**Done when:** gates green; `formatting.py` has no I/O imports (`httpx`, `aiosqlite`, `telegram`).

**Commit:** `feat: Vietnamese text catalog and message formatting`

---

## Prompt 8 — Parcel service (auto-try)

**Goal:** All user-facing parcel rules — carrier detection with auto-try, phone digits, link-only answers, list, resolve, remove, rename, history, default phone — in `ParcelService`, tested against a real temp database and fake carriers.

**Spec:** §4.1, §4.3, §9.10, §6.4 (backoff formula for a failed first fetch).

**Preconditions:** Prompt 7 committed (`services/parcels.py` already holds `AddKind`/`AddOutcome`).

**Modify:** `src/vn_parcel_bot/services/parcels.py` (add `ParcelService`). **Create:** `tests/test_parcels_service.py`.

**Build:**

1. `ParcelService.__init__` stores dependencies; `carriers` is a `Mapping[CarrierCode, Carrier]`.
2. `add(user, raw_code, phone_last4=None, carrier=None)` — exactly §4.3:
   ```
   code = normalize_code(raw_code)
   if carrier is not None:
       if not GENERIC_CODE_RE.match(code): return AddOutcome("invalid_code", code=code or None)
       candidates = [carrier]
   else:
       candidates = detect_carriers(code)
   tracked = [c for c in candidates if is_tracked(c) and c in carriers]
   link_only = [c for c in candidates if not is_tracked(c)]
   if not tracked and not link_only: return AddOutcome("invalid_code", code=code or None)
   if phone_last4 is not None and not is_valid_last4(phone_last4): return AddOutcome("invalid_phone", code=code)
   if not tracked: return AddOutcome("link_only", code=code, link_carriers=tuple(link_only))
   if await repo.find_parcel(uid, code): return AddOutcome("duplicate", code=code)
   if await repo.count_active_parcels(uid) >= settings.max_parcels_per_user: return AddOutcome("limit", code=code)
   last4 = phone_last4 or user.default_phone_last4
   tryable = [c for c in tracked if not needs_phone(c) or last4]
   phone_missing = [c for c in tracked if needs_phone(c) and not last4]
   attempts = []                                   # (carrier, TrackingResult | CarrierError)
   for c in tryable:
       try: r = await carriers[c].fetch(http, code, last4 if needs_phone(c) else None)
       except CarrierError as err: attempts.append((c, err)); continue
       attempts.append((c, r))
       if r.found: break
   now = self._now(); interval = settings.poll_interval
   if attempts and isinstance(attempts[-1][1], TrackingResult) and attempts[-1][1].found:
       c, result = attempts[-1]
       parcel = await repo.add_parcel(user_id=uid, carrier=c, candidates=(c,), tracking_number=code,
                                      phone_last4=last4 if needs_phone(c) else None,
                                      now=now, next_check_at=now + interval)
       await repo.insert_events(parcel.id, result.events, now)
       state = "delivered" if result.delivered else "returned" if result.returned else "in_transit"
       latest = result.latest
       await repo.record_check_success(parcel.id, state=state,
           last_status_text=latest.description if latest else None,
           last_event_at=latest.time if latest else None, next_check_at=now + interval, now=now,
           delivered_at=latest.time if state == "delivered" and latest else None)
       return AddOutcome("added", code=code, parcel=await repo.get_parcel(parcel.id), result=result)
   if phone_missing:
       return AddOutcome("needs_phone", code=code, candidates=tuple(phone_missing))
   resolved = tracked[0] if len(tracked) == 1 else None
   parcel = await repo.add_parcel(user_id=uid, carrier=resolved, candidates=tuple(tracked), tracking_number=code,
                                  phone_last4=last4 if any(needs_phone(c) for c in tracked) else None,
                                  now=now, next_check_at=now + interval)
   errors = [o for _, o in attempts if isinstance(o, CarrierError)]
   if attempts and len(errors) == len(attempts):
       n = parcel.consecutive_failures + 1
       await repo.record_check_failure(parcel.id, next_check_at=now + min(interval * 2**n, MAX_BACKOFF), now=now)
       return AddOutcome("added", code=code, parcel=await repo.get_parcel(parcel.id), error=errors[-1],
                         link_carriers=tuple(link_only))
   not_found = next((o for _, o in reversed(attempts) if isinstance(o, TrackingResult)), None)
   await repo.record_check_success(parcel.id, state="pending", last_status_text=None, last_event_at=None,
                                   next_check_at=now + interval, now=now)
   return AddOutcome("added", code=code, parcel=await repo.get_parcel(parcel.id), result=not_found,
                     link_carriers=tuple(link_only))
   ```
   Catch `DuplicateParcelError` from `add_parcel` (race) → `duplicate`.
3. `list_for(user_id)` → `repo.list_parcels(user_id, terminal_since=now - DELIVERED_VISIBLE_FOR)`.
4. `resolve(user_id, ref)`: `ref = ref.strip()`; `^\d{1,3}$` → 1-based index into `list_for` (out of range → `None`); else `repo.find_parcel(user_id, normalize_code(ref))`.
5. `remove` → resolve, `delete_parcel`, return the parcel (or `None`).
6. `rename(user_id, ref, label)` → resolve; `None`/blank → clear; else `label.strip()[:MAX_LABEL_LENGTH]`; return refreshed parcel.
7. `history(user_id, ref)` → resolve; `repo.list_events(parcel.id, MAX_EVENTS_IN_HISTORY)`.
8. `set_default_phone(user_id, last4)` → `None` clears; invalid → `ValueError`.
9. Log INFO `"parcel added user=%s carrier=%s code=%s state=%s"` with `mask_code(code)` and `parcel.carrier or "auto"`; log INFO `"link-only code user=%s carriers=%s code=%s"`.

**Tests (write first)** — fixtures: `repo` (temp DB), `clock = FakeClock(T0)`, fakes for `spx`, `jt`, `cainiao`, `ninjavan`, `ghn` (**no** `fourpx`, to test the mapping rule), `service = ParcelService(repo, fakes, http=None, settings=settings, now=clock)`, `user = await repo.upsert_user(1, now=T0, name="A", is_allowed=True)`. Codes: `SPX = "SPXVN000000000001"`, `JT = "840000000001"`, `GEN = "GA0000000001"` (ghn, ninjavan), `LP = "LP00000000000001"`, `VNP = "EB123456789VN"`, `FPX = "4PX0000000000000001"`.

- `test_add_invalid_code` — `"hello"` → `invalid_code`; no fetch.
- `test_add_link_only_vnpost` — `link_only`, `link_carriers == ("vnpost",)`, nothing stored, no fetch.
- `test_add_tracked_but_unmapped_is_invalid` — `FPX` → `invalid_code`.
- `test_add_spx_found_in_transit` — `added`, parcel `carrier == "spx"`, `in_transit`, `last_status_text` = latest description, `count_events == 2`, `spx.calls == [(SPX, None)]`.
- `test_add_normalizes_code` — `" spxvn 0000-0000-0000 1"` → stored `SPX`.
- `test_add_spx_delivered_sets_delivered_at`.
- `test_add_spx_not_found_pending_resolved` — `carrier == "spx"`, `pending`, failures 0, `result.found is False`.
- `test_add_single_candidate_error_records_backoff` — `added`, `error` set, failures 1, `next_check_at == T0 + 40 min`.
- `test_add_jt_without_phone_needs_phone` — `needs_phone`, `candidates == ("jt",)`, nothing stored, no fetch.
- `test_add_jt_uses_default_phone` / `test_add_jt_override_wins` / `test_add_jt_invalid_override`.
- `test_add_jt_not_found_mentions_link_only` — `link_carriers == ("best", "viettelpost")`, parcel resolved `jt`.
- `test_add_generic_resolves_second_candidate` — default phone `"1111"`; ghn not found, ninjavan found → `carrier == "ninjavan"`, `phone_last4 is None`, calls ghn then ninjavan.
- `test_add_generic_stops_at_first_found` — ghn found → ninjavan not called; `phone_last4 == "1111"`.
- `test_add_generic_without_phone_tries_ninjavan_then_asks` — no default; ninjavan not found → `needs_phone`, `candidates == ("ghn",)`, `ninjavan.calls` length 1, nothing stored.
- `test_add_generic_without_phone_ninjavan_found` — resolved ninjavan, no question, `ghn.calls == []`.
- `test_add_generic_none_found_stores_unresolved` — with phone: both not found → `carrier is None`, `candidates == ("ghn", "ninjavan")`, `phone_last4 == "1111"`, `pending`.
- `test_add_generic_all_errors_records_failure` — both raise → failures 1, `error.carrier == "ninjavan"`.
- `test_add_generic_error_then_not_found_is_pending_success` — ghn error, ninjavan not found → failures 0, `error is None`.
- `test_add_forced_carrier_skips_detection` — `add(user, "ABC123XYZ", carrier="ninjavan")` → only `ninjavan` called.
- `test_add_forced_carrier_invalid_shape` — `add(user, "A1", carrier="ghn")` → `invalid_code`.
- `test_add_forced_link_only_carrier` — `carrier="ghtk"` → `link_only`, `link_carriers == ("ghtk",)`.
- `test_add_duplicate_any_carrier` — second add of the same code → `duplicate`; fetch count unchanged.
- `test_add_limit` — `MAX_PARCELS_PER_USER="2"` → third active add → `limit`.
- `test_list_for_hides_old_terminal`.
- `test_resolve_by_index_and_code` — `"1"`, `"2"`, code, lowercase code; `"0"`, `"9"` → `None`.
- `test_remove_returns_parcel_and_deletes` / `test_remove_unknown_returns_none`.
- `test_rename_sets_truncates_and_clears`.
- `test_history_returns_recent_events_ascending`.
- `test_set_default_phone_valid_invalid_clear`.
- `test_other_users_parcels_invisible`.

**Verify:** quality gates.

**Done when:** gates green; `pytest --cov=vn_parcel_bot.services.parcels` ≥ 90 %.

**Commit:** `feat: parcel service with carrier auto-detection`

---

## Prompt 9 — Poller

**Goal:** The polling engine: due selection, fetch keys and request de-duplication, polite pacing, carrier resolution for unresolved parcels, diffing, notifications, state transitions, backoff, alerts, quiet hours, housekeeping.

**Spec:** §5.10, §6 (entire), §9.2, §9.11.

**Preconditions:** Prompt 8 committed.

**Create:** `src/vn_parcel_bot/services/poller.py`, `tests/test_poller.py`

**Build:**

1. `Notifier` protocol, `FetchKey`, `fetch_keys`, `PollReport` exactly §9.11. `to_json()` → `json.dumps` of all fields with datetimes as ISO strings, `ensure_ascii=False`.
2. `Poller.__init__` stores deps; `self._lock = asyncio.Lock()`.
3. `run_cycle(*, only_user_id=None, wait=False)`:
   - If `self._lock.locked()` and not `wait` → return `PollReport(started_at=now, finished_at=now, skipped=True)`.
   - `async with self._lock:` run §6.2.
   - Parcels: `repo.active_parcels_for_user(only_user_id)` when given, else `repo.due_parcels(now)`.
   - Fetch phase: ordered unique keys → `by_carrier: dict[CarrierCode, list[FetchKey]]`; `await asyncio.gather(*(self._fetch_carrier(code, keys, outcomes) for code, keys in by_carrier.items()))`. `_fetch_carrier`: `if i > 0: await self._sleep(settings.request_delay_seconds + self._rand() * JITTER_SECONDS)`; `report.fetches += 1`; store the result or the `CarrierError` (and count `report.failures[carrier]`; log WARNING with `mask_code` and `err.reason`).
   - Process phase: §6.2; `report.parcels_checked = len(parcels)`.
4. `_handle_result(parcel, result, now, *, resolved_carrier=None)` — §6.3 steps 1–2. Delivered/returned footer only when `parcel.state` was not already that state. Send via `_notify(parcel.user_id, text)`. `report.new_events += len(new)`.
5. Stale check (§6.3 step 3) — parcels processed this cycle whose refreshed state is `in_transit` and `last_event_at` older than `STALE_AFTER` → `set_state("stale")`, send `format_stale`.
6. `_handle_failure(parcel, err, now)`:
   - `delay = min(settings.poll_interval * 2 ** (parcel.consecutive_failures + 1), MAX_BACKOFF)`; `n = await repo.record_check_failure(parcel.id, next_check_at=now + delay, now=now)`.
   - `n == FAILURE_ALERT_THRESHOLD` → mark `err.carrier` for alert with `(n, str(err))`.
   - Not-found-but-had-events is routed here with `CarrierError(parcel.carrier, "parse", "events disappeared")` (it also counts in `report.failures`).
7. Carrier alerts after processing: alert if marked, or if the carrier had `≥ CARRIER_ALL_FAILED_MIN_FETCHES` fetches and all failed. Cooldown via `meta["alert:<carrier>"]`; send `format_carrier_alert` to `settings.admin_telegram_id` (never silent) and store `now`.
8. `_notify(chat_id, text)`: `silent = self.is_quiet(now)`; `await notifier.send(chat_id, truncate_message(text), silent=silent)`; any exception → log WARNING, continue; `report.messages_sent += 1` only on success.
9. `is_quiet(at)`: `quiet_hours is None` → False; `(start, end)`; `h = at.astimezone(settings.tz).hour`; `start < end` → `start <= h < end`; else `h >= start or h < end`.
10. Housekeeping: `repo.delete_terminal_before(now - PURGE_AFTER)`; `meta["last_poll_report"]`, `meta["last_poll_at"]`; INFO summary line with counts.
11. `only_user_id` cycles do **not** update `last_poll_at` but run everything else.

**Tests (write first)** — fixtures: temp `repo`, `clock = FakeClock(T0)` with `T0 = datetime(2026, 9, 1, 5, 0, tzinfo=UTC)` (12:00 local), fakes `spx`, `jt`, `ghn`, `ninjavan`, `notifier = FakeNotifier()`, `sleeps: list[float]` with `async def fake_sleep(s): sleeps.append(s)`, `rand=lambda: 0.5`, `poller = Poller(repo, fakes, None, notifier, settings, clock, fake_sleep, rand)`. Helper `add(user_id, code, carrier, *, candidates=None, last4=None, due=True)` inserts a parcel via `repo.add_parcel` (`candidates` defaults to `(carrier,)`; pass `carrier=None` for unresolved) with `next_check_at = T0` (due) or `T0 + 1h`. Users 1 (admin id from settings, allowed) and 2 (allowed).

- `test_fetch_keys` — resolved jt with digits → one key with digits; resolved spx → key without digits; unresolved `ghn,ninjavan` without digits → only the ninjavan key; carrier missing from the mapping → skipped.
- `test_no_due_parcels` — report zeros, no calls, no messages.
- `test_skips_not_yet_due`.
- `test_new_events_notify_once` — 2 events → one message with both descriptions; state `in_transit`; second cycle (advance 20 min) same result → no new message.
- `test_only_new_events_in_second_message`.
- `test_same_code_two_users_one_fetch_two_messages`.
- `test_jt_groups_by_phone` — same J&T code with `1111` and `2222` → two fetches.
- `test_pacing_sleeps_between_same_carrier_only` — three SPX parcels + one J&T → `sleeps == [4.0, 4.0]`.
- `test_delivered_transition`; `test_delivered_footer_not_repeated`.
- `test_not_found_young_stays_pending_no_message`.
- `test_not_found_after_seven_days_expires`.
- `test_not_found_with_existing_events_counts_failure`.
- `test_failure_backoff_schedule` — `+40m`, `+80m`, `+160m`, `+320m`, then capped at `+6h`.
- `test_alert_on_fifth_failure_with_cooldown`.
- `test_alert_when_all_fetches_fail_min_three`.
- `test_stale_after_thirty_days`.
- `test_quiet_hours_silent_flag`; `test_is_quiet_wraparound_and_normal_ranges`.
- `test_revoked_user_not_polled`.
- `test_only_user_id_ignores_schedule`.
- `test_skipped_when_locked`.
- `test_notifier_failure_does_not_stop_cycle`.
- `test_purges_old_terminal`; `test_report_saved_to_meta`.
- `test_unresolved_resolves_on_found_candidate` — `carrier=None, candidates=("ghn", "ninjavan"), last4="1111"`; ghn not found, ninjavan found → DB `carrier == "ninjavan"`, `candidates == ("ninjavan",)`; one message with the `UPDATE_RESOLVED` phrase and the events.
- `test_unresolved_prefers_candidate_order` — both found → `ghn`.
- `test_unresolved_all_errors_one_failure` — both raise → `consecutive_failures == 1`; `report.failures == {"ghn": 1, "ninjavan": 1}`.
- `test_unresolved_error_and_not_found_counts_failure` — ghn raises, ninjavan not found → `consecutive_failures == 1`, state stays `pending`, no message.
- `test_unresolved_expires_after_seven_days` — `EXPIRED` sent, state `expired`, carrier still `None`.
- `test_unresolved_without_digits_skips_phone_candidate` — only ninjavan called.
- `test_resolved_next_cycle_uses_single_key` — after resolution, the next due cycle calls only the resolved carrier.

**Verify:** quality gates.

**Done when:** gates green; `pytest --cov=vn_parcel_bot.services.poller` ≥ 90 %.

**Commit:** `feat: poller with carrier resolution, diffing, backoff, alerts, and quiet hours`

---

## Prompt 10 — Telegram bot layer and entry point

**Goal:** Wire everything into a runnable bot: authorization gate, user and admin commands, the phone-digit flow, link-only replies, notifier, job scheduling, error handling, single-instance lock, and `python -m vn_parcel_bot`.

**Spec:** §3, §4, §6.1, §9.4, §9.12, §11, §12.

**Preconditions:** Prompt 9 committed.

**Create:**
- `src/vn_parcel_bot/single_instance.py`
- `src/vn_parcel_bot/bot/__init__.py` (empty), `bot/deps.py`, `bot/parsing.py`, `bot/auth.py`, `bot/commands.py`, `bot/notifier.py`, `bot/handlers_user.py`, `bot/handlers_admin.py`, `bot/app.py`
- `src/vn_parcel_bot/__main__.py`
- `tests/test_single_instance.py`, `tests/test_bot_parsing.py`, `tests/test_auth.py`, `tests/test_notifier.py`, `tests/test_app.py`, `tests/test_main.py`

> Import direction (no cycles): `deps` ← `auth`, `handlers_user`, `handlers_admin` ← `app` ← `__main__`. `deps.py` holds `Deps` and `get_deps` (§9.12); nothing in `bot/` imports `app.py` except `__main__.py`.

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
   - `parse_track_args(args)`: rules under §9.12 (forced carrier alias only when ≥ 2 args; phone digits only when the forced carrier needs a phone or, without one, a remaining candidate does).
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
       def __init__(self, bot: Bot) -> None:
           self._bot = bot

       async def send(self, chat_id: int, text: str, *, silent: bool = False) -> None:
           try:
               await self._bot.send_message(
                   chat_id=chat_id,
                   text=text,
                   parse_mode=ParseMode.HTML,
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
           truncate_message(text),
           parse_mode=ParseMode.HTML,
           link_preview_options=LinkPreviewOptions(is_disabled=True),
       )
   ```
7. `bot/handlers_user.py` — one async function per command; each gets `deps = get_deps(context)`, `user = await deps.repo.get_user(update.effective_user.id)`, `tz = deps.settings.tz`:
   - `start`: `WELCOME.format(name=escape(first_name))` + `"\n\n"` + `HELP`.
   - `help_cmd`: `HELP`.
   - `track_cmd`: `parse_track_args(context.args)`; `None` → `USAGE_TRACK`; else `_add_and_reply(update, context, user, code, last4, carrier)`.
   - `_add_and_reply(update, context, user, code, last4, carrier)`: `outcome = await deps.parcels.add(user, code, last4, carrier)`; if `needs_phone` → `context.user_data["pending_phone"] = {"code": outcome.code, "carrier": carrier}`; else `context.user_data.pop("pending_phone", None)`; reply `format_add_outcome(outcome, tz, max_parcels=settings.max_parcels_per_user)`.
   - `text_message` (`MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE)`):
     - `route = route_text(update.effective_message.text, "pending_phone" in context.user_data)`.
     - `phone_for_pending` → `pending = context.user_data.pop("pending_phone")`; `_add_and_reply(..., pending["code"], route.last4, pending["carrier"])`.
     - `codes` with one code → pop pending; `_add_and_reply(..., code, None, None)`.
     - `codes` with several → pop pending; for each code: `outcome = await deps.parcels.add(user, code)`; collect `needs_phone` codes; reply each other outcome; finally, if collected → `format_needs_phone_multi(collected)`.
     - `invalid_phone` → `INVALID_PHONE`; `unknown` → `UNKNOWN_CODE`.
   - `list_cmd`: `format_parcel_list(await deps.parcels.list_for(uid), tz)`.
   - `status_cmd`: no args → `USAGE_REF.format(command="status")`; `history(uid, " ".join(context.args))`; `None` → `PARCEL_NOT_FOUND`; else `format_history`.
   - `label_cmd`: `parse_ref_and_text`; `None` → `USAGE_LABEL`; `rename`; `None` → `PARCEL_NOT_FOUND`; label set → `LABEL_SET`, cleared → `LABEL_CLEARED`.
   - `remove_cmd`: usage / not found / `REMOVED`.
   - `phone_cmd`: no args → `PHONE_SHOW` or `PHONE_NONE`; `clear` (case-insensitive) → clear + `PHONE_CLEARED`; valid 4 digits → set + `PHONE_SET`; else `INVALID_PHONE`.
   - `check_cmd`: cooldowns in `context.bot_data.setdefault("check_cooldowns", {})`; if `now - last < CHECK_COOLDOWN` → `CHECK_TOO_SOON` with remaining minutes rounded up; else store now, reply `CHECK_STARTED`, `report = await deps.poller.run_cycle(only_user_id=uid, wait=True)`, reply `CHECK_DONE`.
   - `cancel_cmd`: pop `pending_phone` → `CANCELLED` / `NOTHING_TO_CANCEL`.
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
      builder = (
          Application.builder()
          .token(settings.telegram_bot_token)
          .post_init(_post_init)
          .post_shutdown(_post_shutdown)
      )
      if settings.telegram_proxy_url:
          builder = builder.request(HTTPXRequest(proxy=settings.telegram_proxy_url)).get_updates_request(
              HTTPXRequest(proxy=settings.telegram_proxy_url)
          )
      app = builder.build()
      app.bot_data["settings"] = settings
      app.add_handler(TypeHandler(Update, gate), group=-1)
      private = filters.ChatType.PRIVATE
      for name, fn in [
          ("start", start),
          ("help", help_cmd),
          ("track", track_cmd),
          ("list", list_cmd),
          ("status", status_cmd),
          ("label", label_cmd),
          ("remove", remove_cmd),
          ("phone", phone_cmd),
          ("check", check_cmd),
          ("cancel", cancel_cmd),
          ("allow", allow_cmd),
          ("revoke", revoke_cmd),
          ("users", users_cmd),
          ("health", health_cmd),
      ]:
          app.add_handler(CommandHandler(name, fn, filters=private))
      app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & private, text_message))
      app.add_handler(MessageHandler(filters.COMMAND & private, unknown_command))
      app.add_error_handler(on_error)
      return app
      ```
    - `_post_init(app)`: open `Repository`; `now = lambda: datetime.now(UTC)`; upsert admin (`is_allowed=True, is_admin=True`); `http = make_http_client(settings)`; `notifier = TelegramNotifier(app.bot)`; build `ParcelService` and `Poller` with `CARRIERS`; store `Deps` in `bot_data["deps"]`; `app.job_queue.run_repeating(poll_job, interval=settings.poll_interval, first=FIRST_POLL_DELAY_SECONDS, name="poll")`; `await app.bot.set_my_commands(BOT_COMMANDS)`; log INFO `"bot started as @%s"` with `app.bot.username`.
    - `_post_shutdown(app)`: if deps exist → `await http.aclose()`, `await repo.close()`; log INFO `"bot stopped"`.
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
    `_write_startup_error` creates the dir and appends `"<ISO time> <message>\n"` to `startup-error.log` (UTF-8). Load `.env` from the **working directory** only (never `find_dotenv`).

**Tests (write first):**

`tests/test_single_instance.py`
- `test_second_lock_fails_then_succeeds_after_release(tmp_path)`.
- `test_creates_parent_directory`.

`tests/test_bot_parsing.py`
- `test_track_args_none_when_empty`.
- `test_track_args_code_only` — `["SPXVN000000000001"]` → `("SPXVN000000000001", None, None)`.
- `test_track_args_code_with_phone` — `["840000000001", "1234"]` → `("840000000001", "1234", None)`.
- `test_track_args_spaced_spx_digits_stay_in_code` — `["SPXVN", "0000", "0000", "0001"]` → `("SPXVN000000000001", None, None)`.
- `test_track_args_spaced_jt_with_phone` — `["8400", "0000", "0001", "1234"]` → `("840000000001", "1234", None)`.
- `test_track_args_forced_carrier` — `["GA0000000001", "ghn"]` → `("GA0000000001", None, "ghn")`; `["GA0000000001", "1234", "GHN"]` → `("GA0000000001", "1234", "ghn")`.
- `test_track_args_forced_carrier_without_phone_keeps_digits` — `["ABCD1234", "0001", "ninjavan"]` → `("ABCD12340001", None, "ninjavan")`.
- `test_track_args_single_alias_word_is_code` — `["ghn"]` → `("GHN", None, None)`.
- `test_ref_and_text` — `[]` → `None`; `["1"]` → `("1", None)`; `["1", "Áo", "khoác"]` → `("1", "Áo khoác")`.
- `test_route_phone_for_pending` — `("1234", True)` → `phone_for_pending`, `last4="1234"`.
- `test_route_codes_override_pending` — `("SPXVN000000000001", True)` → `codes`.
- `test_route_invalid_phone_when_pending` — `("12", True)` → `invalid_phone`.
- `test_route_unknown` — `("xin chào", False)` → `unknown`; `("1234", False)` → `unknown`.
- `test_route_multiple_codes` — two codes in order.
- `test_route_generic_code_alone` — `("GA0000000001", False)` → `codes`.

`tests/test_auth.py`
- `test_is_authorized_matrix` — admin without DB row ✔; allowed ✔; not allowed ✘; unknown ✘.
- `test_admin_only_blocks_non_admin` — `SimpleNamespace` update/context (`effective_user.id=2`, `effective_message.reply_text` async recorder, `bot_data={"settings": settings}`) → wrapped handler not called, reply contains `ADMIN_ONLY`.
- `test_admin_only_allows_admin`.

`tests/test_notifier.py`
- `test_send_uses_html_silent_and_no_preview`.
- `test_forbidden_is_swallowed`.
- `test_other_errors_propagate`.

`tests/test_app.py`
- `test_build_application_registers_handlers(settings)` — no network: group `-1` holds one `TypeHandler`; the `CommandHandler.commands` in group `0` equal `{start, help, track, list, status, label, remove, phone, check, cancel, allow, revoke, users, health}`; the last handler in group `0` is the unknown-command `MessageHandler`; `len(app.error_handlers) == 1`; `app.bot_data["settings"] is settings`.
- `test_build_application_with_proxy(settings)`.
- `test_bot_commands_match_spec` — names in `BOT_COMMANDS` equal the 10 advertised commands.

`tests/test_main.py`
- `test_config_error_returns_2_and_writes_log(tmp_path, monkeypatch)`.
- `test_second_instance_returns_0(tmp_path, monkeypatch, valid_env)`.

**Verify:**
```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m ruff format --check .
.\.venv\Scripts\python -m pytest -q --cov=vn_parcel_bot --cov-report=term-missing
```
Then a **short live smoke run** (requires `.env`): start `.\.venv\Scripts\python -m vn_parcel_bot`, wait for `bot started as @…` in `logs\bot.log`, stop with Ctrl+C, confirm `bot stopped` logged and no traceback. Skip the smoke run (and say so in the report) if `.env` does not exist yet.

**Done when:** gates green; smoke run starts and stops cleanly (or is reported as pending `.env`); coverage for `carrier_catalog`, `tracking_codes`, `carriers`, `db`, `services` ≥ 85 %.

**Commit:** `feat: telegram bot layer, entry point, and single-instance lock`

---

## Prompt 10A — Live carrier check (GATE)

**Goal:** Prove with **real** tracking codes which tracked carriers return usable data from this PC, replace synthetic fixtures with sanitized live captures, fix parsers where the real shape differs, and settle SPX signing and the J&T phone mechanism. Nothing after this prompt starts until this gate passes.

**Run interactively** — the agent may need you to open a browser's DevTools.

**Spec:** §5 (all), §9.7, §11 (sanitization), §13, §15 R1/R2/R4/R11/R12.

**Preconditions (you):**
- Prompt 10 committed; `.env` filled (Prompt 1 "Then").
- `probe_codes.local.txt` in the repo root (gitignored), one parcel per line, `#` comments allowed:
  ```
  # carrier code [last4]   state-you-believe
  spx      SPXVN0xxxxxxxxxxx      in_transit
  spx      SPXVN0yyyyyyyyyyy      delivered
  jt       84xxxxxxxxxx 1234      in_transit
  cainiao  LPxxxxxxxxxxxxxx       in_transit
  fourpx   4PXxxxxxxxxxxxxxxxx    delivered
  ninjavan SPEVNxxxxxxxxxxx       in_transit
  ghn      GXXXXXXXXXX 5678       in_transit
  ```

**Create/modify:** `scripts/probe_carriers.py` (`--parse`), `tests/test_probe_script.py`, fixtures under `tests/fixtures/<carrier>/`, `tests/fixtures/FIXTURES.md`, carrier modules and their tests as needed, Part 2 §5 of `BUILD_PLAN.md` (then regenerate `SPEC.md`).

**Procedure:**

1. Implement `--parse`: after saving each raw body, wait the pacing delay, call `get_carrier(carrier).fetch(...)` with the same code and digits, and print `found`, event count, `delivered`, `returned`, or the `CarrierError` reason. Test first in `tests/test_probe_script.py` (respx, one carrier, parse path only).
2. `probe_carriers.py telegram` → must print `OK @…`; otherwise stop and have the human fix connectivity (Pre-flight 0.3).
3. `probe_carriers.py carriers --parse`, then inspect the raw files from disk (never paste bodies with personal data into the report):
   - **SPX:** if `tracking_list` is empty for real codes, ask the human to open `https://spx.vn/track` in Chrome with DevTools → Network, search a real code, and share the `fleet_order/tracking/search` request URL and non-cookie headers. If `sls_tracking_number` has the `code|timestamp+hash` form, locate the secret in DevTools → Sources (search `sls_tracking_number` / `SHA256`), set `SPX_SIGNING_SECRET` in `spx.py` with a comment naming the script it came from, and re-probe with `--spx-secret`. Update §5.3.
   - **J&T:** confirm real code + correct digits return events. If not, read `https://jtexpress.vn/plugins/jtexpress/search/assets/js/tracking.js` and `tracking_cellphone.js`, find how the digits are submitted (parameter name, GET vs POST, verify step, cookie/CSRF), update `jt.py` and §5.4, retry. Test one code with wrong digits and record that page.
   - **Cainiao, 4PX, Ninja Van, GHN:** confirm field names and casing, time format and timezone, delivered/returned markers, event order. GHN: test wrong digits once.
   - Probe one **fake** code per carrier for the not-found fixtures if the verified bodies in §5 changed.
   - **BEST (optional, only with a real BEST code):** ask the human to capture the tracking request in DevTools. If it works without captcha, login or signature, write it into §5.1 as a proposal and ask the human before promoting (Appendix B).
4. For each carrier with real data: create sanitized fixtures from the raw captures — real codes → the fake codes of Prompt 2 step 4 (consistent within each file); recipient/sender names, street addresses, full phone numbers, courier names and phones, order IDs → obvious fakes (`Nguyễn Văn A`, `0900000000`, `123 Đường Mẫu`); keep structure, status codes, status texts, hub/city names and timestamps; HTML may drop `<script>`, `<style>`, header/footer but must keep the complete result container and the not-found marker. Overwrite the synthetic files and set provenance `live YYYY-MM-DD` in FIXTURES.md; update the per-file facts. Carriers without real codes keep their synthetic fixtures.
5. Update each affected parser's tests to the live facts (red), fix the parser (green). Update §5 confidence columns and the §5.2 rules if real codes contradict them. Regenerate `SPEC.md` from Part 2.

**Tests (write first):**
- `tests/test_probe_script.py::test_parse_flag_prints_summary_without_body` — respx for Cainiao; captured stdout contains `found=True` and the event count, and does not contain any event description.

**Verify:**
```powershell
.\.venv\Scripts\python scripts\probe_carriers.py telegram
.\.venv\Scripts\python scripts\probe_carriers.py carriers --parse
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m ruff format --check .
git status --short
# No real code may appear in committed files:
Get-Content probe_codes.local.txt | Where-Object { $_ -and -not $_.StartsWith('#') } | ForEach-Object { ($_ -split '\s+')[1] } | ForEach-Object { Select-String -Path tests\fixtures\*\*, tests\fixtures\FIXTURES.md, BUILD_PLAN.md, SPEC.md -Pattern $_ -SimpleMatch }
```
Expected: `OK @…`; each real code shows events (or a recorded decision); tests green; `git status` shows no `_raw/` or `probe_codes.local.txt`; the last command prints **nothing**.

**GATE — stop and report instead of committing if any of these is true:**
- SPX or J&T needs a captcha, a JavaScript challenge, a login, a rotating token from a separate request, or a signing secret that cannot be found.
- Real data could not be obtained for SPX or J&T after the steps above.
- Telegram is unreachable even with the proxy.

Report what you saw and the options: (a) copy browser headers/cookies periodically, (b) headless browser (Playwright) for that carrier, (c) paid aggregator for that carrier, (d) make that carrier link-only. For Cainiao, 4PX, Ninja Van or GHN failures, propose option (d) — §5.1 tier change, `CARRIERS`, catalog and tests — and ask before doing it. The human decides; update Part 2 before any further prompt.

**Done when:** every carrier with real codes is verified or has a recorded human decision in §5; fixtures sanitized with provenance updated; gates green.

**Commit:** `test: verify carriers live and replace synthetic fixtures`

---

## Prompt 11 — Live end-to-end run (interactive)

**Goal:** Prove acceptance scenarios 1–15 (§14) against real Telegram and real carriers, fixing any bug with a regression test first.

**Run interactively** (`agy -i` or Claude Code). The agent drives and checks logs/DB; **you** use Telegram on your phone, plus one family member's account (or a second account) for scenarios 1–2.

**Spec:** §3, §4, §6, §14.

**Preconditions:** Prompt 10A committed (live gate passed); `.env` filled; `probe_codes.local.txt` has in-transit codes for as many tracked carriers as you have (at least SPX, and J&T with digits).

**Create/modify:**
- Modify `src/vn_parcel_bot/db/repo.py` — add dev-support methods (and document them in §9.8 of `BUILD_PLAN.md` in the same commit):
  ```python
  async def parcels_by_code(self, tracking_number: str) -> list[Parcel]: ...
  async def delete_latest_event(
      self, parcel_id: int
  ) -> TrackingEvent | None: ...  # most recent by event_time, id
  async def set_next_check(self, parcel_id: int, when: datetime, now: datetime) -> None: ...
  ```
- Create `scripts/dev_replay_last_event.py` — `python scripts/dev_replay_last_event.py <code>`: loads settings from `.env`, opens `Repository`, for every parcel with that code deletes its latest event and sets `next_check_at = now`; prints parcel id, masked code, and the removed event's local time (never the description).
- Add tests for the three repo methods to `tests/test_repo.py`.
- Create `tests/E2E_RESULTS.md` — table: scenario #, date/time, result (pass/fail), notes (no personal data, masked codes only).

**Procedure:**

1. Write the repo-method tests first, implement, gates green, commit `feat: dev support to replay tracking events`.
2. Human starts the bot in a separate terminal: `.\.venv\Scripts\python -m vn_parcel_bot`. Agent follows `logs\bot.log` (`Get-Content logs\bot.log -Tail 30`) after each step.
3. For each scenario 1–15 in §14, in order:
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
6. When all 15 pass, stop the bot.

**Done when:** scenarios 1–15 recorded as pass; all fixes have regression tests; gates green.

**Commit:** `test: record live end-to-end results for scenarios 1-15`

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
   5. Using the bot: the command table from §4.1 (user commands), automatic carrier detection, link-only carriers, the 4-digit phone rule (J&T, GHN), quiet hours.
   6. Adding family: they send `/start` → forward you the ID → `/allow <id> <name>`; `/revoke`, `/users`.
   7. Operations: status, stop (`Stop-ScheduledTask "VN Parcel Bot"`), start, restart, update (`git pull`, `.\.venv\Scripts\python -m pip install -e .`, restart task), logs location and rotation, DB location, reset (stop task, delete `data\bot.sqlite3`).
   8. Troubleshooting: table from Appendix C of `BUILD_PLAN.md`.
   9. Maintenance: monthly `scripts\probe_carriers.py carriers --parse`; what to do on `ALERT_CARRIER` (Appendix A prompt).
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

**Goal:** Run the remaining acceptance scenarios (§14, 16–19), close any gap between the specification and the code, and tag v1.0.0.

**Run interactively.**

**Spec:** entire document; §12, §14.

**Preconditions:** Prompt 12 committed; the task is installed and running.

**Build / procedure:**

1. **Invalid token handling.** In `__main__.py`, catch `telegram.error.InvalidToken` around `build_application`/`run_polling`: write `"Telegram rejected the bot token"` to `startup-error.log`, log CRITICAL, return `2`. Test first in `tests/test_main.py`: `test_invalid_token_returns_2` (monkeypatch `build_application` to return an object whose `run_polling` raises `InvalidToken`; `bot_data` is a dict).
2. **Drill 16 — logon restart (human):** sign out and back in (or reboot). Within 1 min `status-bot.ps1` shows one process and a fresh `bot started` line. Send `/check` → no duplicate notifications for already-seen events.
3. **Drill 17 — network loss (human):** turn Wi-Fi off 15 min, then on. Expect WARNING lines for carrier `network` errors and PTB network errors, no crash, no user-facing error messages, normal operation after reconnect.
4. **Drill 17b — carrier alert:** with ≥3 active parcels of one carrier (use test codes), stop the task, set `HTTP_TIMEOUT_SECONDS=0.001` in `.env`, run `scripts\run-bot.ps1`, send `/check` → admin receives exactly one `ALERT_CARRIER`; `/check` again after cooldown → no second alert (6 h cooldown). Restore `.env`, stop the foreground bot, `Start-ScheduledTask "VN Parcel Bot"`.
5. **Drill 18 — second instance:** while the task runs, `scripts\run-bot.ps1` → exits within seconds with exit code 0 and log `another instance is running; exiting`.
6. **Drill 19 — token leak scan** (prints counts only, never the token):
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
9. Record drills 16–19 in `tests/E2E_RESULTS.md`; tick every row in **Progress**.
10. After the commit: `git tag v1.0.0`.

**Done when:** drills 16–19 pass; traceability has no gaps; gates green; tag created. Restart the task if any drill stopped it.

**Commit:** `chore: hardening drills, traceability review, v1.0.0`

---

# Part 4 — Appendices

## Appendix A — Maintenance prompt: a carrier changed

Use when the admin receives `ALERT_CARRIER` repeatedly or `/status` shows stale data.

```text
Read BUILD_PLAN.md ("Standing rules" and Part 2 Specification) and tests/fixtures/FIXTURES.md.
The <spx|jt|cainiao|fourpx|ninjavan|ghn> carrier appears broken (admin alerts / parse errors in logs\bot.log).
1. Show the last 50 WARNING/ERROR lines for that carrier from logs\bot.log (masked codes only).
2. Run: .\.venv\Scripts\python scripts\probe_carriers.py carriers --parse  (I have refreshed probe_codes.local.txt).
3. Compare the new raw captures with the committed fixtures and describe exactly what changed.
4. If a captcha, JS challenge, signed/rotating token, or login is now required: STOP and give me the
   Prompt 10A gate options, including making the carrier link-only (§5.1).
5. Otherwise: update FIXTURES.md, replace the sanitized fixtures, update the carrier tests to the new facts (red),
   fix the parser/fetch (green), update §5, regenerate SPEC.md, run all quality gates.
6. Stop-ScheduledTask "VN Parcel Bot"; Start-ScheduledTask "VN Parcel Bot"; ask me to send /check.
7. Commit "fix(<carrier>): adapt to tracking endpoint change".
```

## Appendix B — Future prompt: promote a link-only carrier or add a new one

```text
Read BUILD_PLAN.md ("Standing rules" and Part 2 Specification).
Make carrier <NAME> (code "<code>") tracked:
1. Prove an open endpoint with real codes (DevTools capture by me, then probe_carriers.py). If it needs a captcha,
   JS challenge, signature secret, or login: STOP and report.
2. Update §5.1 (tier, evidence, link template → –), add a §5 subsection with the verified request/response facts,
   §5.2 rules (check overlap with existing rules and the auto-try order), §9.7, §17 CARRIER_NAMES (new code only),
   §14 (one acceptance scenario). A brand-new code also needs a new migration that rebuilds the parcels table
   CHECK constraint; promoting one of the twelve existing codes needs none.
3. Capture sanitized live fixtures (provenance live YYYY-MM-DD).
4. TDD: catalog/tracking_codes tests, carrier parser/fetch tests, registry test, service auto-try test for the new
   candidate order.
5. Register in CARRIERS, regenerate SPEC.md, gates, commit "feat: <NAME> carrier".
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
| J&T/GHN parcel stays "Chưa có thông tin" | Wrong 4 digits, or parcel not yet scanned | Try on the carrier's website with the same digits | `/remove` then `/track <mã> <4 số đúng>` |
| Updates arrive late | PC was asleep/off | Windows power settings | Sleep = Never when plugged in |
| No sound at night | Quiet hours (silent delivery) | `QUIET_HOURS` in `.env` | Change or set empty to disable |
| Family member gets 🔒 | Not allowlisted / revoked | `/users` | `/allow <id> <tên>` |
| `ZoneInfoNotFoundError` | `tzdata` missing | `pip show tzdata` | `pip install -e .` |
| `/list` shows "Đang xác định hãng" for days | No candidate carrier has data yet (label not yet scanned, wrong code or digits) | `/status <ref>` | Wait; or `/remove` then `/track <mã> [4 số] <hãng>` |
| Bot answers a code with links instead of tracking | The code matches a link-only carrier (§5.1), or detection guessed wrong | `/help`; §5.2 rules | Use the links, or `/track <mã> <hãng>` to force a tracked carrier |

## Appendix D — Spec coverage map

| Spec section | Implemented in | Verified in |
|---|---|---|
| §3 Users and access | P6 (users table/repo), P10 (gate, admin) | P6, P10 tests; P11 scenarios 1–2 |
| §4.1 Commands | P10 handlers, P7 texts/formatting | P7, P10 tests; P11 scenarios 3–15 |
| §4.2 Plain-text routing | P10 `bot/parsing.py`, P3 `extract_codes` | P3, P10 tests; P11 scenarios 4, 7, 13 |
| §4.3 Adding a parcel (auto-try) | P8 `ParcelService.add` | P8 tests; P11 scenarios 3–7, 12–15 |
| §4.4 Link lists | P3 catalog links, P7 `format_links` | P3, P7 tests; P11 scenarios 14–15 |
| §5.1 Catalog | P3 `carrier_catalog.py`, P5B registry | P3, P5B tests; P10A |
| §5.2 Detection, order numbers, code-like fallback | P3 `tracking_codes.py` | P3 tests; P10A corrections |
| §5.3–5.8 Carrier facts | P2 fixtures, P4, P5, P5A, P5B | Carrier tests; P10A live gate |
| §5.9 Fetch contract | P2 (`http.py`, `common.py`), P4–P5B | P2 and carrier tests |
| §5.10 Politeness | P9 | P9 pacing/grouping tests |
| §6 Polling and notifications | P9; schedule in P10 | P9 tests; P11 scenarios 8–9, 13 |
| §7 Data model | P6 | P6 tests |
| §8–9 Architecture and interfaces | P1–P10 | Per-prompt tests; P13 traceability |
| §10 Configuration | P1 | P1 tests |
| §11 Logging, security, privacy | P1 (logging), P2/P10A (sanitizing), P10 | P1 tests; P10A verify; P13 drill 19 |
| §12 Runtime on Windows | P10 (lock, exit codes), P12 (task), P13 (InvalidToken) | P10, P13 tests; P12 verify; P13 drills 16–18 |
| §13 Testing strategy | all prompts | quality gates on every prompt |
| §14 Acceptance scenarios | – | P11 (1–15), P13 (16–19) |
| §17 Text catalog | P7 `texts.py` | P7 tests; P11 wording checks |
