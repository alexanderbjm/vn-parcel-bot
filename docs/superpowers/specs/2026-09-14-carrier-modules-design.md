# Carrier modules with hot reload, BEST through 17TRACK, 15-digit Cainiao codes — design

Date: 2026-09-14 · Branch: `main` · Status: Parts A and B built (`2aa4ba4`, `8c76d2d`, `1ca8d76`, `829a31c`, `3824184`) and verified live on 2026-09-14; Part C was dropped from this plan, but agy's 17TRACK client was kept at the user's choice and reviewed (`de07e97`)

## 1. Why

- **Fixing one carrier touches shared files.** A carrier is spread over `carrier_catalog.py` (tier, phone, link), the first-match rule table in `tracking_codes.py`, `texts.CARRIER_NAMES`, special cases in `services/formatting.py` (JNTX and Lazada notes) and a client in `carriers/<code>.py`. The database pins the carrier list with a CHECK. The user wants each carrier to be one module that can be fixed on its own while the bot keeps running.
- **BEST Express is link-only.** Its track page (`best-inc.vn/track`) shows a slider captcha (checked in Chrome on 2026-09-14). The user first chose the official 17TRACK Tracking API, then dropped BEST from this work: it stays link-only.
- **15-digit Cainiao codes were rejected.** A Cainiao waybill `77344…898` (15 digits) was answered as an order number. The user wants no carrier words and no extra reply lines: every 15-digit number is tracked as Cainiao.
- **insane-search was not installed.** The user asked for `fivetaku/insane-search`. Its README describes getting past CAPTCHAs, WAF blocks and anti-bot challenges (browser TLS impersonation, headless browsers). Using it on BEST's captcha is captcha bypass, which this project does not do, so it is not part of this design.

## 2. Decisions (from the chat)

| Topic | Decision |
|---|---|
| "Without interrupting" | Hot reload: a changed carrier module is reloaded by the running bot after a self-check; a failing module keeps its last working version and the admin is told. No restart. |
| Structure | Approach A: one Python file per carrier under `carriers/modules/`, holding everything about that carrier. (Rejected: YAML data files with code clients that still need restarts; a supervisor that restarts the bot on file change.) |
| BEST | Not in this work (dropped 2026-09-14). BEST stays link-only; the 17TRACK Tracking API (key `101194`, "BEST Inc (VN)") remains a later option. |
| Typed or read 15-digit numbers | Always added as pending Cainiao parcels. Order numbers that get no Cainiao data expire after `PENDING_EXPIRY` (7 days) with the usual expiry message. |
| Carrier words / hint lines | None. Users never name the carrier; no new reply lines. The existing JNTX and Lazada pending notes stay. |
| Screenshot order numbers | Codes the reader returns under `order_ids` keep today's order-only reply. |

Planning changes (2026-09-14): `build_client()` takes no argument; `CarrierModule.order` sets display order; `/help` lists carriers through `format_help()`; the reply-to-label and prompt clean-up work was added to the same plan as Task 8 (`fea23f3`).

Out of scope: captcha or anti-bot tooling of any kind (including insane-search), BEST Express tracking and any 17TRACK client, hot reload of shared code (contract, registry, `carriers/common.py`, services, bot), SF Express or JNTX through 17TRACK (possible later by editing only their module files; 17TRACK keys `100012` and `100295`), 17TRACK `stoptrack`/webhooks, per-user carrier settings.

## 3. Part A — carrier modules and the registry

### 3.1 Module contract (`carriers/api.py`)

```python
@dataclass(frozen=True)
class Rule:
    pattern: str              # re.fullmatch on the normalized code, re.ASCII
    priority: int             # 100 prefixed/unique format, 60 carrier-specific numeric, 40 shared numeric, 10 generic
    rank: int = 0             # tie order between modules sharing a priority (lower first)
    standalone_only: bool = False  # only when the whole message is this code

@dataclass(frozen=True)
class ModuleContext:
    settings: Settings

@dataclass(frozen=True)
class CarrierModule:
    code: str                 # [a-z0-9]{2,20}, equals the file name
    display_name: str         # plain text; formatting escapes it
    rules: tuple[Rule, ...]
    needs_phone: bool = False
    link_template: str | None = None               # https URL, optional {code}
    examples: tuple[tuple[str, bool], ...] = ()    # (code, detected as this carrier?)
    build_client: Callable[[ModuleContext], Carrier | None] = lambda ctx: None
    pending_hint: Callable[[str], str | None] = lambda code: None  # HTML text appended to pending/needs-phone replies
```

A module is **tracked** when `build_client` returns a client, otherwise **link-only**, which requires `link_template`. `Carrier` and the result/error models stay in `carriers/models.py`; `CarrierCode` becomes `str`.

### 3.2 Modules

`carriers/modules/` holds `spx.py`, `jt.py`, `cainiao.py`, `fourpx.py`, `ninjavan.py`, `ghn.py`, `best.py`, `yunexpress.py`, `ghtk.py`, `viettelpost.py`, `vnpost.py`, `lex.py`, `sf.py`. Each file defines `MODULE` and contains its own parser and client (moved from `carriers/<code>.py`, which are deleted), its links and its Vietnamese hint text. The package stays importable normally so tests can import parsers.

Rules, reproducing today's detection except the new 15-digit rule:

| Module | Rule | Priority | Rank | Notes |
|---|---|---|---|---|
| spx | `SPXVN[0-9A-Z]{8,16}` | 100 | | |
| ninjavan | `SPEVN[0-9A-Z]{6,20}` | 100 | | |
| cainiao | `LP\d{14}`, `[A-Z]{2}\d{9}CN`, `YT\d{13}` | 100 | | `pending_hint` = today's Lazada note for `YT\d{13}` |
| cainiao | `\d{15}` | 60 | | new |
| fourpx | `4PX[0-9A-Z]{10,20}` | 100 | | |
| yunexpress | `YT\d{16}` | 100 | | |
| vnpost | `[A-Z]{2}\d{9}VN` | 100 | | |
| lex | `(LEXVN\|LXVN\|LVS)[0-9A-Z]{6,20}` | 100 | | |
| ghtk | `S\d{5,10}(\.[0-9A-Z]{1,12}){1,4}` | 100 | | |
| jt | `JNTX[A-Z]?\d{8,12}` | 100 | | `pending_hint` = today's J&T cross-border note |
| sf | `SF\d{13}` | 100 | | |
| best | `BEST[A-Z]{0,6}\d{8,16}VN[A-Z]{0,3}` | 100 | | |
| best | `\d{13}` | 60 | | |
| jt / best / viettelpost | `\d{12}` | 40 | 0 / 1 / 2 | |
| ghn / ninjavan | `(?=[0-9A-Z]*[A-Z])(?=[0-9A-Z]*\d)[0-9A-Z]{8,14}` | 10 | 0 / 1 | `standalone_only` |

### 3.3 Snapshot and detection (`carriers/registry.py`)

`CarrierSnapshot` is immutable: `modules: Mapping[str, LoadedModule]` (module, client or `None`, file hash).

- `detect(code) -> DetectResult(candidates: tuple[str, ...], standalone_only: bool)`: every rule of every module that full-matches; keep the highest priority; candidates ordered by `(rank, code)`; `standalone_only` is true only if every kept rule is standalone-only.
- `get(code) -> LoadedModule | None`, `is_tracked(code)`, `needs_phone(code)`, `link(code, tracking_number) -> str | None`, `pending_hint(tracking_number, code) -> str | None`, `clients() -> Mapping[str, Carrier]`.

`CarrierRegistry` holds `current: CarrierSnapshot`. Services take the registry and read `registry.current` once per operation, so a swap never changes carriers halfway through an add or a poll.

### 3.4 Core changes

- `tracking_codes.py` keeps only carrier-neutral functions: `normalize_code` (including the Lazada `\d{15}_` prefix drop), `extract_codes(text, snapshot)`, `is_order_number` (used by the vision fallback), `is_seller_fleet`, `is_code_like`, `is_valid_last4`, `mask_code`. `is_jt_cross_border` and `is_lazada_cainiao` move into their modules.
- `seventeen_track_url` moves from `carrier_catalog.py` to `services/formatting.py` unchanged.
- Deleted: `carrier_catalog.py`, `texts.CARRIER_NAMES`, the carrier `CARRIERS` dict, `AddKind` `"order_number"` and `texts.ORDER_NUMBER` (15-digit numbers now detect as Cainiao before that check). `HELP` lists carriers from the snapshot.
- `ParcelService`, `Poller`, `bot/parsing.py`, `services/formatting.py` and the photo handler receive the registry. Formatting escapes `display_name` and appends `snapshot.pending_hint(...)` where it appends the JNTX/Lazada notes today.
- A parcel whose carrier (or every candidate) has no loaded module is skipped by the poller with one WARNING per cycle (`carrier module missing carrier=%s parcels=%d`); `/list`, `/status` and digests show it with the stored code as its carrier name.

### 3.5 Database (migration 2)

- Before migrating a file database at `user_version` 1, the bot writes `VACUUM INTO '<db_path>.bak-v1'` (skipped for `:memory:`; an existing backup is not overwritten).
- Migration 2 rebuilds `parcels` without the carrier CHECK, following SQLite's table-rebuild procedure: `PRAGMA foreign_keys=OFF` outside the transaction, then in one transaction create `parcels_new` (same columns and other constraints), copy all rows, drop `parcels`, rename, recreate `idx_parcels_due`; `PRAGMA foreign_key_check` must return nothing; `PRAGMA foreign_keys=ON`; `user_version = 2`. Events and their parcel ids are unchanged.
- `Repository.add_parcel`/`resolve_carrier` stop checking carriers; `ParcelService` only stores carriers present in the snapshot.

## 4. Part B — hot reload

- `CarrierRegistry.refresh()` runs from a JobQueue job every 30 s (`carrier modules`), off the poll job.
- For each `modules/*.py` it computes a SHA-256 of the file bytes. A file whose hash differs from the live version is **debounced**: it loads only once the same new hash is seen on two consecutive checks (avoids half-saved files).
- Loading: `importlib.util.spec_from_file_location("vn_parcel_bot.carriers.modules._live_<code>_<hash8>", path)`, put in `sys.modules` under that unique name while it executes and while it is live; the previous version's entry is removed after a successful swap. Module files must not do I/O at import time (review rule, stated at the top of `api.py`).
- Validation of a candidate snapshot (the current modules with this file replaced): `MODULE` exists and is a `CarrierModule`; `code` equals the file stem and matches `[a-z0-9]{2,20}`; every pattern compiles; link-only modules have an `https://` `link_template`; `build_client(context)` does not raise; **every module's** `examples` still hold against the candidate snapshot (so a new rule cannot take codes from another carrier).
- Pass: `current` is replaced by the candidate snapshot in one assignment; INFO `carrier module reloaded code=%s hash=%s tracked=%s`.
- Fail: `current` is unchanged; WARNING `carrier module rejected code=%s hash=%s error=%s` (exception type and line, no file contents); one admin message per `(code, hash)` via meta key `module-rejected:<code>`: `texts.MODULE_REJECTED` = `"⚠️ Module <code>{code}</code> lỗi, vẫn dùng bản cũ: {error}"`.
- A new valid file adds a carrier. A deleted file keeps its last working version with one WARNING per file hash (`carrier module file missing code=%s, keeping last version`). At startup every file must load; a module that fails at startup is skipped with the same WARNING and admin message, and the bot still starts.
- Only `modules/*.py` reloads. Changes to any other file still need the safe restart.

## 5. Part C — BEST through 17TRACK (dropped)

Dropped by the user on 2026-09-14. `modules/best.py` is link-only with today's rules and link. Notes kept for later: 17TRACK v2.4 charges one quota per registered number, `gettrackinfo` is free, error `-18019902` means not registered, `-18019901` already registered, `-18019908` quota used up.

## 6. Testing

- **Regression:** today's `test_detect_each_rule`, `extract_codes`, parsing and formatting tests run against the real `modules/` directory; 15-digit cases now expect `["cainiao"]`.
- **Registry (tmp module directories):** loads all; `detect` priority/rank/standalone behaviour; rejected module keeps the old version and alerts once per hash; debounce needs two equal hashes; an example conflict between two modules is rejected; deleted file kept; new file added; startup with one broken module still starts.
- **Hot reload end to end:** a Poller with a registry over a tmp copy of a module; the module file is edited between two cycles; the second cycle uses the new parser without recreating the Poller.
- **Migration:** a version-1 file database with parcels and events migrates to version 2 with identical rows and events, accepts a carrier outside the old list, writes the backup once; `:memory:` skips the backup.
- Existing gates: ruff check, ruff format, full pytest; no real codes or keys in tests or fixtures.

## 7. Build order

1. Part A: contract, modules, registry (static load), core wiring, migration 2 — behaviour unchanged except 15-digit numbers.
2. Part B: refresh job, debounce, validation, admin alert.
3. Docs: BUILD_PLAN 2.0 (§5 carrier modules, §9 contract, schema v2, reload runbook), regenerated SPEC, README (how to fix a carrier module live).
