# Daily digests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every allowed user gets a Telegram summary of their parcels at 07:00, 12:00, 19:00 and 22:00 local time, with 🆕 on parcels that changed since the previous digest; instant updates stay as they are.

**Architecture:** `DIGEST_TIMES` in `Settings`; `Repository.parcel_ids_with_events_since`; `format_digest` reusing the `/list` line layout; `services/digest.py` with `DigestService.build`/`send_all` storing the per-user cutoff in `meta`; `bot/app.py` gains `schedule_jobs` (poll + one `run_daily` per slot) and `digest_job`.

**Tech Stack:** Python 3.13, python-telegram-bot 22 JobQueue (`run_daily`), aiosqlite, pytest (asyncio auto mode), ruff (line length 100).

**Spec:** `docs/superpowers/specs/2026-09-14-spx-browser-vision-digests-design.md` §5 and §6

## Global Constraints

- Run tools through the venv from `C:\Users\hozkg\projects\vn-parcel-bot`.
- Digests are sent with sound (`silent=False`); instant update behaviour and quiet hours are unchanged.
- `cutoff = now()` is taken once per digest run before any query; after a successful send `meta["digest:last:<user_id>"] = cutoff.isoformat()`; a failed send leaves it unchanged; a Telegram `Forbidden` (handled inside `TelegramNotifier.send`) counts as sent.
- First digest window: 24 hours. Users with nothing to show get no message and no meta update. Users with `is_allowed = False` are skipped.
- A slot missed while the bot is down is skipped (no catch-up).
- No real tracking codes in committed files. Stage files by explicit path. Every commit message ends with:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01JNknSSDZMR9Cg8iyhqGxQN
  ```
- Gates before every commit: `ruff check . --fix`, `ruff format .`, then `ruff check .`, `ruff format --check .` and full `pytest` green.

---

### Task 1: `DIGEST_TIMES` setting

**Files:**
- Modify: `src/vn_parcel_bot/config.py`
- Modify: `tests/test_config.py`

**Interfaces:**
- Produces: `config.DEFAULT_DIGEST_TIMES: tuple[datetime.time, ...]`; `Settings.digest_times: tuple[datetime.time, ...]` (naive times, sorted, de-duplicated; `()` disables).

- [ ] **Step 1: Write the failing tests** in `tests/test_config.py`: change `from datetime import timedelta` to `from datetime import time, timedelta`; add `    assert s.digest_times == (time(7), time(12), time(19), time(22))` to the defaults test; after the defaults test add:

```python
def test_digest_times_custom_and_empty(valid_env):
    custom = Settings.from_env({**valid_env, "DIGEST_TIMES": "22:00, 7:30,12:00,07:30"})
    assert custom.digest_times == (time(7, 30), time(12), time(22))
    assert Settings.from_env({**valid_env, "DIGEST_TIMES": "  "}).digest_times == ()


@pytest.mark.parametrize("value", ["25:00", "7", "07:60", "abc", "07:00,"])
def test_digest_times_rejected(valid_env, value):
    with pytest.raises(ConfigError) as exc:
        Settings.from_env({**valid_env, "DIGEST_TIMES": value})
    assert "DIGEST_TIMES" in str(exc.value)
```

- [ ] **Step 2: Run and confirm failure** — `.\.venv\Scripts\python -m pytest tests/test_config.py -q` → `AttributeError: 'Settings' object has no attribute 'digest_times'` and `DID NOT RAISE`.

- [ ] **Step 3: Implement** in `src/vn_parcel_bot/config.py`:
1. `from datetime import timedelta` → `from datetime import time, timedelta`.
2. After `_VISION_ENGINES = …` add:

```python
_DIGEST_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
DEFAULT_DIGEST_TIMES = (time(7), time(12), time(19), time(22))
```

3. After `default_claude_code_path` add:

```python
def _digest_times(env: Mapping[str, str], errors: list[str]) -> tuple[time, ...]:
    if "DIGEST_TIMES" not in env:
        return DEFAULT_DIGEST_TIMES
    raw = env["DIGEST_TIMES"].strip()
    if not raw:
        return ()
    slots: set[time] = set()
    for part in raw.split(","):
        match = _DIGEST_TIME_RE.match(part.strip())
        hour, minute = (int(match.group(1)), int(match.group(2))) if match else (-1, -1)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            errors.append("DIGEST_TIMES must be comma-separated HH:MM times (00:00..23:59) or empty")
            return DEFAULT_DIGEST_TIMES
        slots.add(time(hour, minute))
    return tuple(sorted(slots))
```

4. In `Settings`, after `telegram_proxy_url: str | None = None` add `    digest_times: tuple[time, ...] = DEFAULT_DIGEST_TIMES`.
5. In `from_env`, directly before `        if errors:` add `        digest_times = _digest_times(env, errors)`; in `return cls(...)` after `telegram_proxy_url=proxy,` add `            digest_times=digest_times,`.

- [ ] **Step 4: Run and confirm pass**, then the full gates.
- [ ] **Step 5: Commit** `src/vn_parcel_bot/config.py tests/test_config.py` — "feat: DIGEST_TIMES setting".

---

### Task 2: Building and sending digests

**Files:**
- Modify: `src/vn_parcel_bot/db/repo.py`, `src/vn_parcel_bot/services/formatting.py`, `src/vn_parcel_bot/texts.py`, `src/vn_parcel_bot/constants.py`
- Create: `src/vn_parcel_bot/services/digest.py`, `tests/test_digest.py`

**Interfaces:**
- Consumes: `Repository.list_users`, `list_parcels(user_id, terminal_since=)`, `get_meta`, `set_meta`, `add_parcel`, `record_check_success`, `insert_events`, `set_label`; `Parcel.is_active`; `tests.fakes.FakeClock`, `FakeNotifier`, `ev`.
- Produces: `Repository.parcel_ids_with_events_since(user_id, since) -> set[int]`; `formatting.format_digest(parcels, changed_ids, at, tz) -> str`; `constants.FIRST_DIGEST_WINDOW`; `texts.DIGEST_HEADER`, `DIGEST_NEW_MARK`, `DIGEST_FOOTER`, `DIGEST_FOOTER_FINISHED`; `digest.DIGEST_META_PREFIX = "digest:last:"`; `DigestService(repo, notifier, settings, now)` with `async build(user_id, cutoff) -> str | None` and `async send_all() -> int`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_digest.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest

from tests.fakes import FakeClock, FakeNotifier, ev
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.digest import DIGEST_META_PREFIX, DigestService

T0 = datetime(2026, 9, 14, 0, 0, tzinfo=UTC)  # 07:00 in Asia/Ho_Chi_Minh


@pytest.fixture
async def repo(tmp_path):
    r = await Repository.open(tmp_path / "digest.sqlite3")
    yield r
    await r.close()


@pytest.fixture
def clock():
    return FakeClock(T0)


async def allowed_user(repo, telegram_id=1):
    return await repo.upsert_user(
        telegram_id, now=T0 - timedelta(days=3), name="A", is_allowed=True
    )


async def add_parcel(
    repo, user_id, code, *, state="pending", label=None, updated=None, event_at=None
):
    created = T0 - timedelta(days=2)
    parcel = await repo.add_parcel(
        user_id=user_id,
        carrier="spx",
        candidates=("spx",),
        tracking_number=code,
        phone_last4=None,
        now=created,
        next_check_at=created + timedelta(minutes=20),
    )
    if label:
        await repo.set_label(parcel.id, label, created)
    touched = updated or created
    moving = state != "pending"
    await repo.record_check_success(
        parcel.id,
        state=state,
        last_status_text="Đang giao hàng" if moving else None,
        last_event_at=touched if moving else None,
        next_check_at=touched + timedelta(minutes=20),
        now=touched,
        delivered_at=touched if state == "delivered" else None,
    )
    if event_at is not None:
        await repo.insert_events(parcel.id, [ev(0, base=event_at)], event_at)
    return await repo.get_parcel(parcel.id)


async def test_build_returns_none_without_parcels(repo, settings, clock):
    await allowed_user(repo)
    assert await DigestService(repo, FakeNotifier(), settings, clock).build(1, T0) is None


async def test_first_digest_lists_parcels_and_marks_recent_events(repo, settings, clock):
    await allowed_user(repo)
    await add_parcel(repo, 1, "SPXVN000000000001", label="Ốp lưng", event_at=T0 - timedelta(days=2))
    await add_parcel(
        repo,
        1,
        "SPXVN000000000002",
        state="in_transit",
        label="Tai nghe",
        updated=T0 - timedelta(hours=1),
        event_at=T0 - timedelta(hours=1),
    )
    text = await DigestService(repo, FakeNotifier(), settings, clock).build(1, T0)
    assert text.startswith("🗓 <b>Tóm tắt đơn hàng</b> · 07:00")
    lines = text.splitlines()
    old_line = next(line for line in lines if "Ốp lưng" in line)
    new_line = next(line for line in lines if "Tai nghe" in line)
    assert "🆕" not in old_line
    assert new_line.endswith("🆕")
    assert text.endswith("Đang theo dõi 2 đơn")


async def test_finished_parcel_is_shown_once(repo, settings, clock):
    await allowed_user(repo)
    await add_parcel(
        repo, 1, "SPXVN000000000003", state="delivered", label="Sạc", updated=T0 - timedelta(hours=2)
    )
    notifier = FakeNotifier()
    digests = DigestService(repo, notifier, settings, clock)
    assert await digests.send_all() == 1
    text = notifier.sent[0][1]
    assert "Sạc" in text
    assert "🆕" in text
    assert text.endswith("Đang theo dõi 0 đơn · 1 đơn vừa kết thúc")
    clock.advance(timedelta(hours=5))
    assert await digests.build(1, clock()) is None


async def test_event_saved_while_sending_is_marked_next_time(repo, settings, clock):
    await allowed_user(repo)
    parcel = await add_parcel(repo, 1, "SPXVN000000000004", event_at=T0 - timedelta(days=2))

    class SlowNotifier(FakeNotifier):
        async def send(self, chat_id, text, *, silent=False):
            await super().send(chat_id, text, silent=silent)
            clock.advance(timedelta(seconds=30))
            await repo.insert_events(parcel.id, [ev(0, "Đã đến kho", base=clock())], clock())
            clock.advance(timedelta(seconds=30))

    digests = DigestService(repo, SlowNotifier(), settings, clock)
    assert await digests.send_all() == 1
    assert await repo.get_meta(f"{DIGEST_META_PREFIX}1") == T0.isoformat()
    clock.advance(timedelta(hours=5))
    assert "🆕" in await digests.build(1, clock())


async def test_failed_send_keeps_previous_since(repo, settings, clock):
    await allowed_user(repo)
    await add_parcel(repo, 1, "SPXVN000000000005")
    notifier = FakeNotifier(fail_with=RuntimeError("telegram down"))
    assert await DigestService(repo, notifier, settings, clock).send_all() == 0
    assert await repo.get_meta(f"{DIGEST_META_PREFIX}1") is None


async def test_send_all_only_allowed_users_with_something_to_show(repo, settings, clock):
    await allowed_user(repo, 1)
    await allowed_user(repo, 2)
    await repo.upsert_user(3, now=T0, name="C", is_allowed=False)
    await add_parcel(repo, 1, "SPXVN000000000006")
    await add_parcel(repo, 3, "SPXVN000000000007")
    notifier = FakeNotifier()
    assert await DigestService(repo, notifier, settings, clock).send_all() == 1
    assert [(chat_id, silent) for chat_id, _, silent in notifier.sent] == [(1, False)]
    assert await repo.get_meta(f"{DIGEST_META_PREFIX}1") == T0.isoformat()
    assert await repo.get_meta(f"{DIGEST_META_PREFIX}2") is None


async def test_parcel_ids_with_events_since(repo):
    await allowed_user(repo, 1)
    await allowed_user(repo, 2)
    await add_parcel(repo, 1, "SPXVN000000000008", event_at=T0 - timedelta(days=2))
    recent = await add_parcel(repo, 1, "SPXVN000000000009", event_at=T0)
    await add_parcel(repo, 2, "SPXVN000000000010", event_at=T0)
    assert await repo.parcel_ids_with_events_since(1, T0 - timedelta(hours=1)) == {recent.id}
```

- [ ] **Step 2: Run and confirm failure** — `.\.venv\Scripts\python -m pytest tests/test_digest.py -q` → `ModuleNotFoundError: No module named 'vn_parcel_bot.services.digest'`.

- [ ] **Step 3: Implement**

`src/vn_parcel_bot/constants.py`: append `FIRST_DIGEST_WINDOW = timedelta(hours=24)`.

`src/vn_parcel_bot/texts.py`: append

```python

DIGEST_HEADER = "🗓 <b>Tóm tắt đơn hàng</b> · {time}"
DIGEST_NEW_MARK = " 🆕"
DIGEST_FOOTER = "Đang theo dõi {active} đơn"
DIGEST_FOOTER_FINISHED = " · {finished} đơn vừa kết thúc"
```

`src/vn_parcel_bot/db/repo.py`: after `list_parcels` add

```python
    async def parcel_ids_with_events_since(self, user_id: int, since: datetime) -> set[int]:
        rows = await self._fetchall(
            "SELECT DISTINCT e.parcel_id FROM events e JOIN parcels p ON p.id = e.parcel_id "
            "WHERE p.user_id = ? AND e.created_at >= ?",
            (user_id, _to_db(since)),
        )
        return {int(row[0]) for row in rows}
```

`src/vn_parcel_bot/services/formatting.py`:
1. `from collections.abc import Mapping, Sequence` → `from collections.abc import Collection, Mapping, Sequence`.
2. Replace the whole `format_parcel_list` function with:

```python
def _list_item(index: int, parcel: Parcel, tz: ZoneInfo, mark: str = "") -> str:
    status = (
        _escape(parcel.last_status_text)
        if parcel.last_status_text
        else texts.STATE_TEXT[parcel.state]
    )
    suffix = (
        texts.LIST_TIME_SUFFIX.format(time=format_time(parcel.last_event_at, tz))
        if parcel.last_event_at
        else ""
    )
    carrier = (
        carrier_name(parcel.carrier) if parcel.carrier is not None else texts.CARRIER_UNRESOLVED
    )
    return texts.LIST_ITEM.format(
        index=index,
        emoji=texts.STATE_EMOJI[parcel.state],
        title=parcel_title(parcel),
        carrier=carrier + mark,
        status=status,
        time_suffix=suffix,
    )


def format_parcel_list(parcels: Sequence[Parcel], tz: ZoneInfo) -> str:
    if not parcels:
        return texts.LIST_EMPTY
    items = [_list_item(index, parcel, tz) for index, parcel in enumerate(parcels, start=1)]
    return truncate_message(texts.LIST_HEADER + "\n\n" + "\n".join(items))


def format_digest(
    parcels: Sequence[Parcel], changed_ids: Collection[int], at: datetime, tz: ZoneInfo
) -> str:
    items = []
    for index, parcel in enumerate(parcels, start=1):
        is_new = parcel.id in changed_ids or not parcel.is_active
        items.append(_list_item(index, parcel, tz, texts.DIGEST_NEW_MARK if is_new else ""))
    active = sum(1 for parcel in parcels if parcel.is_active)
    finished = len(parcels) - active
    footer = texts.DIGEST_FOOTER.format(active=active)
    if finished:
        footer += texts.DIGEST_FOOTER_FINISHED.format(finished=finished)
    header = texts.DIGEST_HEADER.format(time=at.astimezone(tz).strftime("%H:%M"))
    return truncate_message(header + "\n\n" + "\n".join(items) + "\n\n" + footer)
```

Create `src/vn_parcel_bot/services/digest.py`:

```python
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from vn_parcel_bot.config import Settings
from vn_parcel_bot.constants import FIRST_DIGEST_WINDOW
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.formatting import format_digest

log = logging.getLogger(__name__)

DIGEST_META_PREFIX = "digest:last:"


class DigestNotifier(Protocol):
    async def send(self, chat_id: int, text: str, *, silent: bool = False) -> None: ...


class DigestService:
    def __init__(
        self,
        repo: Repository,
        notifier: DigestNotifier,
        settings: Settings,
        now: Callable[[], datetime],
    ) -> None:
        self._repo = repo
        self._notifier = notifier
        self._settings = settings
        self._now = now

    async def build(self, user_id: int, cutoff: datetime) -> str | None:
        stored = await self._repo.get_meta(f"{DIGEST_META_PREFIX}{user_id}")
        since = datetime.fromisoformat(stored) if stored else cutoff - FIRST_DIGEST_WINDOW
        parcels = await self._repo.list_parcels(user_id, terminal_since=since)
        if not parcels:
            return None
        changed = await self._repo.parcel_ids_with_events_since(user_id, since)
        return format_digest(parcels, changed, cutoff, self._settings.tz)

    async def send_all(self) -> int:
        cutoff = self._now()
        sent = 0
        for user in await self._repo.list_users():
            if not user.is_allowed:
                continue
            text = await self.build(user.telegram_id, cutoff)
            if text is None:
                continue
            try:
                await self._notifier.send(user.telegram_id, text, silent=False)
            except Exception:
                log.warning("digest send failed user=%s", user.telegram_id, exc_info=True)
                continue
            await self._repo.set_meta(f"{DIGEST_META_PREFIX}{user.telegram_id}", cutoff.isoformat())
            sent += 1
        log.info("digest run sent=%s", sent)
        return sent
```

- [ ] **Step 4: Run and confirm pass** — `.\.venv\Scripts\python -m pytest tests/test_digest.py tests/test_formatting.py -q`, then the full gates.
- [ ] **Step 5: Commit** `src/vn_parcel_bot/db/repo.py src/vn_parcel_bot/services/formatting.py src/vn_parcel_bot/texts.py src/vn_parcel_bot/constants.py src/vn_parcel_bot/services/digest.py tests/test_digest.py` — "feat: build and send daily digests".

---

### Task 3: Scheduling

**Files:**
- Modify: `src/vn_parcel_bot/bot/app.py`, `src/vn_parcel_bot/bot/deps.py`
- Create: `tests/test_scheduling.py`

**Interfaces:**
- Consumes: `DigestService` (Task 2), `Settings.digest_times` (Task 1).
- Produces: `Deps.digests: DigestService | None`; `app.digest_job(context)`; `app.schedule_jobs(job_queue, settings)`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_scheduling.py`:

```python
from dataclasses import replace
from datetime import time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from vn_parcel_bot.bot.app import digest_job, poll_job, schedule_jobs


class FakeJobQueue:
    def __init__(self):
        self.repeating = []
        self.daily = []

    def run_repeating(self, callback, **kwargs):
        self.repeating.append((callback, kwargs))

    def run_daily(self, callback, **kwargs):
        self.daily.append((callback, kwargs))


def test_schedule_jobs_registers_poll_and_four_digests(settings):
    queue = FakeJobQueue()
    schedule_jobs(queue, settings)
    assert [(callback, kwargs["name"]) for callback, kwargs in queue.repeating] == [
        (poll_job, "poll")
    ]
    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    assert [kwargs["time"] for _, kwargs in queue.daily] == [
        time(7, tzinfo=tz),
        time(12, tzinfo=tz),
        time(19, tzinfo=tz),
        time(22, tzinfo=tz),
    ]
    assert all(kwargs["time"].tzinfo == tz for _, kwargs in queue.daily)
    assert all(callback is digest_job for callback, _ in queue.daily)
    assert [kwargs["name"] for _, kwargs in queue.daily] == [
        "digest 07:00",
        "digest 12:00",
        "digest 19:00",
        "digest 22:00",
    ]


def test_schedule_jobs_without_digests(settings):
    queue = FakeJobQueue()
    schedule_jobs(queue, replace(settings, digest_times=()))
    assert queue.daily == []
    assert len(queue.repeating) == 1


async def test_digest_job_runs_the_service():
    calls = []

    class Digests:
        async def send_all(self):
            calls.append(True)
            return 1

    context = SimpleNamespace(bot_data={"deps": SimpleNamespace(digests=Digests())})
    await digest_job(context)
    assert calls == [True]
```

- [ ] **Step 2: Run and confirm failure** — `.\.venv\Scripts\python -m pytest tests/test_scheduling.py -q` → `ImportError: cannot import name 'digest_job'`.

- [ ] **Step 3: Implement**

`src/vn_parcel_bot/bot/deps.py`: add `from vn_parcel_bot.services.digest import DigestService` to the imports and `    digests: DigestService | None = None` after the `vision` field.

`src/vn_parcel_bot/bot/app.py`:
1. Add `JobQueue,` to the `from telegram.ext import (...)` list and `from vn_parcel_bot.services.digest import DigestService` to the imports.
2. In `_post_init` replace

```python
    app.bot_data["deps"] = Deps(settings, repo, http, parcels, poller, notifier, vision=vision)
    assert app.job_queue is not None, "install python-telegram-bot[job-queue]"
    app.job_queue.run_repeating(
        poll_job, interval=settings.poll_interval, first=FIRST_POLL_DELAY_SECONDS, name="poll"
    )
```

with

```python
    digests = DigestService(repo, notifier, settings, _utc_now)
    app.bot_data["deps"] = Deps(
        settings, repo, http, parcels, poller, notifier, vision=vision, digests=digests
    )
    assert app.job_queue is not None, "install python-telegram-bot[job-queue]"
    schedule_jobs(app.job_queue, settings)
```

3. After `poll_job` add:

```python
async def digest_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    digests = get_deps(context).digests
    if digests is not None:
        await digests.send_all()


def schedule_jobs(job_queue: JobQueue, settings: Settings) -> None:
    job_queue.run_repeating(
        poll_job, interval=settings.poll_interval, first=FIRST_POLL_DELAY_SECONDS, name="poll"
    )
    for slot in settings.digest_times:
        job_queue.run_daily(
            digest_job,
            time=slot.replace(tzinfo=settings.tz),
            name=f"digest {slot.strftime('%H:%M')}",
        )
    if settings.digest_times:
        log.info(
            "digests scheduled at %s",
            ", ".join(slot.strftime("%H:%M") for slot in settings.digest_times),
        )
```

- [ ] **Step 4: Run and confirm pass** — `.\.venv\Scripts\python -m pytest tests/test_scheduling.py tests/test_app.py -q`, then the full gates.
- [ ] **Step 5: Commit** `src/vn_parcel_bot/bot/app.py src/vn_parcel_bot/bot/deps.py tests/test_scheduling.py` — "feat: schedule daily digests".

---

### Task 4: Docs and spec 1.5

**Files:** `.env.example`, `README.md`, `BUILD_PLAN.md`, `SPEC.md`, the design doc, this plan.

- [ ] **Step 1: Write and run** `E:\Temp\claude\C--Users-hozkg\bfbff226-59df-4322-9e19-aa36ae7aa76c\scratchpad\update_docs_digest_15.py`, which (asserting each anchor occurs exactly once before writing anything):
  - `.env.example`: after `QUIET_HOURS=22-7\n` insert `# Local times for the daily order digest (comma-separated HH:MM); set empty to disable\nDIGEST_TIMES=07:00,12:00,19:00,22:00\n`.
  - `README.md`: before the row starting `   | \`VISION_ENGINE\` |` insert `   | \`DIGEST_TIMES\` | no | \`07:00,12:00,19:00,22:00\` | Local times for the daily digest; empty disables it |\n`; before `\n## Adding family and friends\n` insert a `### Daily digests` paragraph: at each digest time every allowed user with parcels gets one summary with sound, listing active parcels with 🆕 on those that changed since the previous digest and parcels that finished since then shown once; instant updates still arrive as before; set `DIGEST_TIMES` in `.env` (or leave it empty to turn digests off) and restart the bot.
  - `BUILD_PLAN.md`: `Version 1.4` → `Version 1.5` in the header line; a `## Changes in 1.5 (2026-09-14)` entry before `## Changes in 1.4` ("**Daily digests** (§6, §10, §17): …; details and tests in the design doc §5"); a `### Daily digests (\`services/digest.py\`)` section inserted before the first `\n## 7.` after `# Part 2 — Specification` with the Global Constraints of this plan as bullets; a §10 row `| \`DIGEST_TIMES\` | no | \`07:00,12:00,19:00,22:00\` | comma-separated local HH:MM; empty disables |` after the `ANTHROPIC_WORKSPACE_ID` row; the four `DIGEST_*` texts after the `VISION_UNSUPPORTED_IMAGE` block in §17. Regenerate `SPEC.md` from Part 2 with the header comment `(version 1.5)`.
  - Design doc: in the status line replace `Part B revised to Claude Code (approved in chat); Part A approved` with `Part B built (\`a07a1cc\`…\`13d8ca2\`); Part A built`.
- [ ] **Step 2: Verify** `git diff --stat` lists only those files; gates green.
- [ ] **Step 3: Commit** those files plus `docs/superpowers/plans/2026-09-14-daily-digests.md` — "docs: spec 1.5, daily digests".

---

### Task 5: Restart and check

- [ ] **Step 1:** Restart the "VN Parcel Bot" task safely (stop the task, stop leftover bot processes and wait, start the task).
- [ ] **Step 2:** `logs/bot.log` shows `bot started as @vn_parcel_hozk_bot` followed by `digests scheduled at 07:00, 12:00, 19:00, 22:00`, and no errors. The next digest arrives at the next slot; its log line is `digest run sent=1`.
