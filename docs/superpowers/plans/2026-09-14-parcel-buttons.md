# Parcel Buttons, Stickers and Service-Bot Patterns Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parcel cards with inline buttons (rename, history, check, remove, share, tracking link) that edit in place, numbered pickers with pagination on `/list` and digests, carrier stickers mapped by the admin, sound only on big moments, flood-control retry and share links.

**Architecture:** `vn_parcel_bot/keyboards.py` builds every `InlineKeyboardMarkup` from parcels; `bot/handlers_callback.py` handles all callback queries statelessly from `callback_data`; `services/sharing.py` owns share tokens in `meta`; the poller gains `check_parcel`, the sound rule, stickers and card buttons; `TelegramNotifier` gains `reply_markup`, `send_sticker` and one `RetryAfter` retry.

**Tech Stack:** Python 3.13, python-telegram-bot 22.8, aiosqlite, pytest (asyncio auto), ruff 0.16.7.

**Spec:** `docs/superpowers/specs/2026-09-14-parcel-buttons-design.md`

## Global Constraints

- Test first: write the test, run it red, implement, run green.
- Gates before every commit (PowerShell, repo root): `.\.venv\Scripts\ruff check . --fix` and `.\.venv\Scripts\ruff format .` on the task's files, then `ruff check . --output-format concise`, `ruff format --check .`, `python -m pytest -q`. Commit explicit paths only, with `git commit -F <message file>` (PowerShell 5.1 breaks messages containing double quotes); messages end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01JNknSSDZMR9Cg8iyhqGxQN`.
- `callback_data` never contains a tracking code and stays under 64 bytes.
- Every callback handler answers the query; ownership (`parcel.user_id == query.from_user.id`) is checked before any action.
- No real codes, tokens or sticker file ids in tests or commits.
- Planning decisions beyond the spec: keyboards live in `vn_parcel_bot/keyboards.py` (the poller and digest service use them, so not under `bot/`); tracked carriers without a module link get a 17TRACK button labelled `🔗 Tra cứu 17TRACK ↗`; cards opened from a digest use list page 1 for `⬅ Danh sách`.

## File Structure

| File | Responsibility |
|---|---|
| `src/vn_parcel_bot/keyboards.py` (new) | `card_keyboard`, `back_keyboard`, `confirm_remove_keyboard`, `list_keyboard`, `list_back_keyboard`, `share_open_keyboard` |
| `src/vn_parcel_bot/services/sharing.py` (new) | `share_token`, `shared_parcel` |
| `src/vn_parcel_bot/bot/handlers_callback.py` (new) | `callback_query` dispatcher and actions |
| `src/vn_parcel_bot/services/formatting.py` | `format_parcel_card`, `parcel_link`, paged `format_parcel_list`, `list_pages` |
| `src/vn_parcel_bot/bot/notifier.py` | `reply_markup`, `send_sticker`, `RetryAfter` retry |
| `src/vn_parcel_bot/services/poller.py` | `check_parcel`, sound rule, stickers, card buttons on updates |
| `src/vn_parcel_bot/services/digest.py` | digest picker keyboard |
| `src/vn_parcel_bot/bot/handlers_user.py` | `reply(..., reply_markup)`, card buttons on adds, paged `/list`, rename refreshes the card, `/start s_<token>` |
| `src/vn_parcel_bot/bot/handlers_admin.py` | `/sticker` |
| `src/vn_parcel_bot/bot/app.py` | `CallbackQueryHandler`, `/sticker` |
| `src/vn_parcel_bot/db/repo.py` | `delete_meta` |
| `src/vn_parcel_bot/constants.py`, `texts.py` | `LIST_PAGE_SIZE`, `OUT_FOR_DELIVERY_PROGRESS`, button and share/sticker texts |

---

### Task 1: Cards, keyboards, notifier and repo helpers

**Files:** Create `src/vn_parcel_bot/keyboards.py`, `tests/test_keyboards.py`; modify `formatting.py`, `texts.py`, `constants.py`, `bot/notifier.py`, `db/repo.py`, `tests/fakes.py`, `tests/test_notifier.py`, `tests/test_formatting.py`, `tests/test_repo.py`.

**Interfaces (produces):**
- `constants.LIST_PAGE_SIZE = 5`, `constants.OUT_FOR_DELIVERY_PROGRESS = 95`.
- `formatting.format_parcel_card(parcel, tz) -> str`; `formatting.parcel_link(parcel) -> tuple[str, str]` (button name, url); `formatting.list_pages(count) -> int`; `formatting.format_parcel_list(parcels, tz, *, page=1) -> str` (global numbering, `LIST_PAGE` footer when more than one page).
- `keyboards.card_keyboard(parcel, *, page=None)`, `keyboards.back_keyboard(parcel_id, page=None)`, `keyboards.confirm_remove_keyboard(parcel_id, page=None)`, `keyboards.list_keyboard(numbered: Sequence[tuple[int, Parcel]], page, pages) -> InlineKeyboardMarkup | None`, `keyboards.list_back_keyboard(page)`, `keyboards.share_open_keyboard(token)`.
- `TelegramNotifier(bot, sleep=asyncio.sleep)`; `send(chat_id, text, *, silent=False, reply_markup=None) -> None`; `send_sticker(chat_id, file_id) -> bool` (False only on `BadRequest`).
- `Repository.delete_meta(key) -> None`.
- `tests.fakes.FakeNotifier`: records `sent` (unchanged tuples), `markups: list`, `stickers: list[tuple[int, str]]`, `sticker_ok: bool`.

- [ ] **Step 1: Tests.** `tests/test_keyboards.py`:

```python
from datetime import UTC, datetime

from tests.test_formatting import make_parcel
from vn_parcel_bot.keyboards import (
    back_keyboard,
    card_keyboard,
    confirm_remove_keyboard,
    list_back_keyboard,
    list_keyboard,
    share_open_keyboard,
)


def cells(markup):
    return [[button.callback_data or button.url for button in row] for row in markup.inline_keyboard]


def labels(markup):
    return [[button.text for button in row] for row in markup.inline_keyboard]


def test_card_keyboard_buttons_and_data():
    markup = card_keyboard(make_parcel(id=42))
    assert labels(markup) == [
        ["✏️ Đổi tên", "📜 Hành trình"],
        ["🔄 Kiểm tra", "🗑 Xóa"],
        ["📤 Chia sẻ", "🔗 Tra cứu 17TRACK ↗"],
    ]
    data = cells(markup)
    assert data[0] == ["p:42:ren", "p:42:his"]
    assert data[1] == ["p:42:chk", "p:42:del"]
    assert data[2][0] == "p:42:shr"
    assert data[2][1] == "https://t.me/" or data[2][1].startswith("https://t.17track.net/vi#nums=")
    assert all(len(d.encode()) < 64 for row in data for d in row if not d.startswith("https"))


def test_card_keyboard_from_list_has_back_row_and_page():
    data = cells(card_keyboard(make_parcel(id=7), page=2))
    assert data[0] == ["p:7:ren:2", "p:7:his:2"]
    assert data[-1] == ["l:2"]


def test_link_only_carrier_uses_its_page():
    parcel = make_parcel(id=3, carrier="vnpost", candidates=("vnpost",), tracking_number="EB123456789VN")
    row = card_keyboard(parcel).inline_keyboard[2]
    assert row[1].text == "🔗 Tra cứu VNPost ↗"
    assert row[1].url.startswith("https://vnpost.vn/")


def test_small_keyboards():
    assert cells(back_keyboard(5)) == [["p:5:card"]]
    assert cells(back_keyboard(5, 3)) == [["p:5:card:3"]]
    assert cells(confirm_remove_keyboard(5, 1)) == [["p:5:dok:1", "p:5:dno:1"]]
    assert labels(confirm_remove_keyboard(5)) == [["✅ Xóa", "↩ Hủy"]]
    assert cells(list_back_keyboard(4)) == [["l:4"]]
    assert cells(share_open_keyboard("AbC-123_xyz0")) == [["s:AbC-123_xyz0:ok", "s:AbC-123_xyz0:no"]]


def test_list_keyboard_numbers_and_navigation():
    numbered = [(index, make_parcel(id=10 + index)) for index in range(6, 11)]
    markup = list_keyboard(numbered, page=2, pages=3)
    assert labels(markup)[0] == ["6", "7", "8", "9", "10"]
    assert cells(markup)[0][0] == "p:16:card:2"
    assert cells(markup)[-1] == ["l:1", "l:2", "l:3"]
    assert labels(markup)[-1] == ["⬅️", "2/3", "➡️"]
    assert list_keyboard([], page=1, pages=1) is None
    single = list_keyboard([(1, make_parcel(id=1))], page=1, pages=1)
    assert cells(single) == [["p:1:card:1"]]
```

(`make_parcel` lives in `tests/test_formatting.py`; the test uses it as a helper.) Replace the doubtful URL assertion line `assert data[2][1] == "https://t.me/" or ...` with `assert data[2][1].startswith("https://t.17track.net/vi#nums=")`.

Append to `tests/test_formatting.py`:

```python
def test_parcel_card_shows_title_progress_bar_and_status():
    parcel = make_parcel(label="Áo", last_status_text="Đã đến kho", last_event_at=T0, progress=50)
    assert format_parcel_card(parcel, TZ) == (
        "🚚 <b>Áo</b> · SPX · 50%\n🟩🟩🟩🟩🟩🟥🟥🟥🟥🟥\nĐã đến kho · 🕒 01/09 08:30"
    )
    pending = format_parcel_card(unresolved(), TZ)
    assert pending.startswith(f"⏳ <b>{blurred('GA0000000001')}</b> · GHN / Ninja Van\n")


def test_parcel_link_prefers_module_link():
    assert parcel_link(make_parcel()) == ("17TRACK", f"https://t.17track.net/vi#nums={SPX}")
    vnpost = make_parcel(carrier="vnpost", candidates=("vnpost",), tracking_number="EB123456789VN")
    name, url = parcel_link(vnpost)
    assert name == "VNPost" and url.startswith("https://vnpost.vn/")


def test_parcel_list_pages():
    parcels = [make_parcel(id=i, label=f"Đơn {i}", tracking_number=f"SPXVN00000000000{i}") for i in range(1, 8)]
    assert list_pages(7) == 2 and list_pages(0) == 1
    first = format_parcel_list(parcels, TZ)
    assert "5. " in first and "6. " not in first and first.endswith("Trang 1/2")
    second = format_parcel_list(parcels, TZ, page=2)
    assert "6. " in second and "7. " in second and "1. " not in second
```

(import `format_parcel_card`, `parcel_link`, `list_pages`.)

`tests/test_notifier.py`: `FakeBot` gains `send_sticker(**kwargs)` recording into `self.stickers` and raising `self.sticker_error` if set; add:

```python
async def test_send_passes_reply_markup():
    bot = FakeBot()
    marker = object()
    await TelegramNotifier(bot).send(5, "x", reply_markup=marker)
    assert bot.calls[0]["reply_markup"] is marker


async def test_retry_after_is_retried_once():
    bot = FakeBot()
    failures = [RetryAfter(3)]
    original = bot.send_message

    async def flaky(**kwargs):
        if failures:
            raise failures.pop()
        await original(**kwargs)

    bot.send_message = flaky
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    await TelegramNotifier(bot, sleep=fake_sleep).send(5, "x")
    assert sleeps == [3]
    assert len(bot.calls) == 1


async def test_send_sticker_reports_bad_request():
    bot = FakeBot()
    assert await TelegramNotifier(bot).send_sticker(5, "file-1") is True
    assert bot.stickers[0]["disable_notification"] is True
    bot.sticker_error = BadRequest("Wrong file identifier")
    assert await TelegramNotifier(bot).send_sticker(5, "file-1") is False
```

`tests/test_repo.py`: `test_delete_meta` (set, delete, get is None; deleting a missing key is fine).

- [ ] **Step 2: Red.** `pytest tests/test_keyboards.py tests/test_formatting.py tests/test_notifier.py tests/test_repo.py -q` fails (imports).

- [ ] **Step 3: Implement.**

`constants.py`: `LIST_PAGE_SIZE = 5`, `OUT_FOR_DELIVERY_PROGRESS = 95`.

`texts.py` (after `DIGEST_FOOTER_FINISHED`):

```python
CARD_HEADER = "{emoji} <b>{title}</b> · {carrier}"
CARD_NOT_FOUND = "Không tìm thấy đơn này."
LIST_PAGE = "Trang {page}/{pages}"
BTN_RENAME = "✏️ Đổi tên"
BTN_HISTORY = "📜 Hành trình"
BTN_CHECK = "🔄 Kiểm tra"
BTN_REMOVE = "🗑 Xóa"
BTN_SHARE = "📤 Chia sẻ"
BTN_LINK = "🔗 Tra cứu {name} ↗"
BTN_BACK = "⬅ Quay lại"
BTN_BACK_LIST = "⬅ Danh sách"
BTN_CONFIRM_REMOVE = "✅ Xóa"
BTN_CANCEL = "↩ Hủy"
BTN_TRACK_SHARED = "✅ Theo dõi"
BTN_SKIP = "↩ Bỏ qua"
BTN_PREV = "⬅️"
BTN_NEXT = "➡️"
SHARE_LINK = "📤 Gửi link này để người khác theo dõi <b>{title}</b>:\n{link}"
SHARE_OPEN = "📦 Bạn được chia sẻ đơn <b>{title}</b> · {carrier}. Theo dõi đơn này?"
SHARE_NOT_FOUND = "Link chia sẻ này không còn dùng được."
STICKER_SET = "🎨 Đã lưu sticker cho {carrier}."
STICKER_REMOVED = "🎨 Đã xóa sticker của {carrier}."
STICKER_LIST = "🎨 Hãng có sticker: {carriers}"
STICKER_USAGE = "Cách dùng: trả lời một sticker bằng /sticker &lt;hãng&gt;, hoặc /sticker &lt;hãng&gt; off"
STICKER_UNKNOWN = "Không có hãng này. Các hãng: {carriers}"
```

`formatting.py`:

```python
def format_parcel_card(parcel: Parcel, tz: ZoneInfo) -> str:
    progress_suffix, bar = _progress_parts(parcel.progress, parcel.state)
    status = (
        _escape(parcel.last_status_text)
        if parcel.last_status_text
        else texts.STATE_TEXT[parcel.state]
    )
    time_suffix = (
        texts.LIST_TIME_SUFFIX.format(time=format_time(parcel.last_event_at, tz))
        if parcel.last_event_at
        else ""
    )
    lines = [
        texts.CARD_HEADER.format(
            emoji=texts.STATE_EMOJI[parcel.state],
            title=parcel_title(parcel),
            carrier=parcel_carrier_label(parcel) + progress_suffix,
        )
    ]
    if bar:
        lines.append(bar)
    lines.append(status + time_suffix)
    return "\n".join(lines)


def parcel_link(parcel: Parcel) -> tuple[str, str]:
    if parcel.carrier is not None:
        snapshot = current_snapshot()
        url = snapshot.link(parcel.carrier, parcel.tracking_number)
        if url:
            return snapshot.display_name(parcel.carrier), url
    return texts.LINK_17TRACK_NAME, seventeen_track_url(parcel.tracking_number)


def list_pages(count: int) -> int:
    return max(1, math.ceil(count / LIST_PAGE_SIZE))
```

`format_parcel_list(parcels, tz, *, page=1)`: clamp `page` to `1..list_pages(len(parcels))`, take `parcels[(page-1)*5 : page*5]` numbered from `(page-1)*5 + 1`, append `"\n\n" + texts.LIST_PAGE.format(page=page, pages=pages)` when `pages > 1` (before `truncate_message`). Import `math` and `LIST_PAGE_SIZE`.

`keyboards.py`:

```python
from collections.abc import Sequence

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from vn_parcel_bot import texts
from vn_parcel_bot.db.repo import Parcel
from vn_parcel_bot.services.formatting import parcel_link

NUMBERS_PER_ROW = 5


def _button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data)


def _page(page: int | None) -> str:
    return "" if page is None else f":{page}"


def card_keyboard(parcel: Parcel, *, page: int | None = None) -> InlineKeyboardMarkup:
    prefix, suffix = f"p:{parcel.id}", _page(page)
    name, url = parcel_link(parcel)
    rows = [
        [_button(texts.BTN_RENAME, f"{prefix}:ren{suffix}"), _button(texts.BTN_HISTORY, f"{prefix}:his{suffix}")],
        [_button(texts.BTN_CHECK, f"{prefix}:chk{suffix}"), _button(texts.BTN_REMOVE, f"{prefix}:del{suffix}")],
        [_button(texts.BTN_SHARE, f"{prefix}:shr{suffix}"), InlineKeyboardButton(texts.BTN_LINK.format(name=name), url=url)],
    ]
    if page is not None:
        rows.append([_button(texts.BTN_BACK_LIST, f"l:{page}")])
    return InlineKeyboardMarkup(rows)


def back_keyboard(parcel_id: int, page: int | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_button(texts.BTN_BACK, f"p:{parcel_id}:card{_page(page)}")]])


def confirm_remove_keyboard(parcel_id: int, page: int | None = None) -> InlineKeyboardMarkup:
    suffix = _page(page)
    return InlineKeyboardMarkup([[
        _button(texts.BTN_CONFIRM_REMOVE, f"p:{parcel_id}:dok{suffix}"),
        _button(texts.BTN_CANCEL, f"p:{parcel_id}:dno{suffix}"),
    ]])


def list_back_keyboard(page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_button(texts.BTN_BACK_LIST, f"l:{page}")]])


def list_keyboard(
    numbered: Sequence[tuple[int, Parcel]], page: int, pages: int
) -> InlineKeyboardMarkup | None:
    if not numbered:
        return None
    buttons = [_button(str(number), f"p:{parcel.id}:card:{page}") for number, parcel in numbered]
    rows = [buttons[i : i + NUMBERS_PER_ROW] for i in range(0, len(buttons), NUMBERS_PER_ROW)]
    if pages > 1:
        previous = page - 1 if page > 1 else pages
        following = page + 1 if page < pages else 1
        rows.append([
            _button(texts.BTN_PREV, f"l:{previous}"),
            _button(f"{page}/{pages}", f"l:{page}"),
            _button(texts.BTN_NEXT, f"l:{following}"),
        ])
    return InlineKeyboardMarkup(rows)


def share_open_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        _button(texts.BTN_TRACK_SHARED, f"s:{token}:ok"),
        _button(texts.BTN_SKIP, f"s:{token}:no"),
    ]])
```

`bot/notifier.py`:

```python
import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta

from telegram import Bot, LinkPreviewOptions
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, RetryAfter

log = logging.getLogger(__name__)
MAX_RETRY_WAIT_SECONDS = 60


def _seconds(value: int | timedelta) -> float:
    return value.total_seconds() if isinstance(value, timedelta) else float(value)


class TelegramNotifier:
    def __init__(self, bot: Bot, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        self._bot = bot
        self._sleep = sleep

    async def _with_retry(self, call: Callable[[], Awaitable[object]]) -> None:
        try:
            await call()
        except RetryAfter as exc:
            await self._sleep(min(_seconds(exc.retry_after), MAX_RETRY_WAIT_SECONDS))
            await call()

    async def send(self, chat_id: int, text: str, *, silent: bool = False, reply_markup: object = None) -> None:
        try:
            await self._with_retry(
                lambda: self._bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    disable_notification=silent,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                    reply_markup=reply_markup,
                )
            )
        except Forbidden:
            log.info("user %s blocked the bot", chat_id)

    async def send_sticker(self, chat_id: int, file_id: str) -> bool:
        try:
            await self._with_retry(
                lambda: self._bot.send_sticker(chat_id=chat_id, sticker=file_id, disable_notification=True)
            )
        except Forbidden:
            log.info("user %s blocked the bot", chat_id)
        except BadRequest:
            return False
        return True
```

`repo.py`: `async def delete_meta(self, key: str) -> None: await self._write("DELETE FROM meta WHERE key = ?", (key,))`.

`tests/fakes.py` `FakeNotifier`: `send(self, chat_id, text, *, silent=False, reply_markup=None)` appends to `sent` and `markups`; `sticker_ok = True`, `stickers = []`, `async def send_sticker(self, chat_id, file_id): self.stickers.append((chat_id, file_id)); return self.sticker_ok`. Update `SlowNotifier.send` in `tests/test_digest.py` to accept `reply_markup=None`.

- [ ] **Step 4: Green + gates + commit** `Add parcel cards, keyboards, sticker send and flood retry helpers`.

---

### Task 2: Poller — check one parcel, sound rule, stickers, card buttons; digest picker

**Files:** `services/poller.py`, `services/digest.py`, `tests/test_poller.py`, `tests/test_digest.py`.

**Interfaces:**
- `Poller.check_parcel(user_id: int, parcel_id: int) -> Parcel | None` (None when missing or not the user's; runs the normal path only for active parcels; returns the reloaded parcel).
- `Notifier` protocol: `send(chat_id, text, *, silent=False, reply_markup=None)`, `send_sticker(chat_id, file_id) -> bool`.
- Update messages: `reply_markup=card_keyboard(reloaded parcel)`; silent unless big moment (newly delivered, newly returned, or progress reached `OUT_FOR_DELIVERY_PROGRESS` now and was below before); big moments follow quiet hours as before.
- Sticker: meta `sticker:<result.carrier>` sent via `send_sticker` just before the update; a `False` result adds the carrier to `self._broken_stickers` with one WARNING `carrier sticker failed carrier=%s`.
- `DigestService.send_all` sends `reply_markup=list_keyboard(list(enumerate(parcels, 1)), page=1, pages=1)`.

- [ ] **Step 1: Tests** (append to `tests/test_poller.py`):

```python
async def test_update_message_has_card_buttons_and_is_silent(poller, repo, fakes, notifier, settings):
    parcel = await add(repo, SPX, "spx")
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Đã đến kho"))
    await poller.run_cycle()
    chat_id, text, silent = notifier.sent[0]
    assert silent is True
    markup = notifier.markups[0]
    assert markup.inline_keyboard[0][0].callback_data == f"p:{parcel.id}:ren"


async def test_out_for_delivery_and_delivered_ring(poller, repo, fakes, notifier, clock):
    await add(repo, SPX, "spx")
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Đang giao hàng"))
    await poller.run_cycle()
    assert notifier.sent[-1][2] is False
    clock.advance(timedelta(hours=1))
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Đang giao hàng"), ev(5, "Giao hàng thành công"), delivered=True)
    await poller.run_cycle()
    assert notifier.sent[-1][2] is False


async def test_sticker_sent_before_update_and_skipped_after_failure(poller, repo, fakes, notifier, clock, caplog):
    await repo.set_meta("sticker:spx", "file-spx")
    await add(repo, SPX, "spx")
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Đã đến kho"))
    await poller.run_cycle()
    assert notifier.stickers == [(USER, "file-spx")]
    notifier.sticker_ok = False
    clock.advance(timedelta(hours=1))
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Đã đến kho"), ev(5, "Rời kho"))
    await poller.run_cycle()
    clock.advance(timedelta(hours=1))
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Đã đến kho"), ev(5, "Rời kho"), ev(9, "Đến kho 2"))
    await poller.run_cycle()
    assert len(notifier.stickers) == 2
    assert caplog.text.count("carrier sticker failed carrier=spx") == 1
    assert len(notifier.sent) == 3


async def test_check_parcel_only_checks_that_parcel(poller, repo, fakes):
    first = await add(repo, SPX, "spx")
    await add(repo, "SPXVN000000000002", "spx")
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Đang giao hàng"))
    checked = await poller.check_parcel(USER, first.id)
    assert checked.progress == 95
    assert fakes["spx"].calls == [(SPX, None)]
    assert await poller.check_parcel(999, first.id) is None
```

Existing poller tests that assert the silent flag of ordinary update messages (`rg -n "sent\[.*\]\[2\]|silent" tests/test_poller.py`) change to expect `True`, except delivered/returned ones.

`tests/test_digest.py`: in `test_send_all_only_allowed_users_with_something_to_show` assert `notifier.markups[0].inline_keyboard[0][0].callback_data.startswith("p:")`.

- [ ] **Step 2: Red.**

- [ ] **Step 3: Implement.** In `Poller.__init__`: `self._broken_stickers: set[str] = set()`. Protocol `Notifier` updated. `run_cycle` unchanged; `_cycle(self, only_user_id, only_parcels: list[Parcel] | None = None)` uses `only_parcels` when given and writes `last_poll_at` only when both are None.

```python
    async def check_parcel(self, user_id: int, parcel_id: int) -> Parcel | None:
        async with self._lock:
            parcel = await self._repo.get_parcel(parcel_id)
            if parcel is None or parcel.user_id != user_id:
                return None
            if parcel.is_active:
                await self._cycle(None, only_parcels=[parcel])
            return await self._repo.get_parcel(parcel_id)
```

In `_handle_result`, replace the notify block:

```python
            if new or newly_delivered or newly_returned:
                shown = _shown_progress(parcel.progress, progress)
                text = format_event_update(
                    parcel, new, self._settings.tz,
                    delivered=newly_delivered, returned=newly_returned,
                    resolved_carrier=resolved_carrier, progress=shown,
                )
                reached = (
                    progress is not None
                    and progress >= OUT_FOR_DELIVERY_PROGRESS
                    and (parcel.progress or 0) < OUT_FOR_DELIVERY_PROGRESS
                )
                big_moment = newly_delivered or newly_returned or reached
                current = await self._repo.get_parcel(parcel.id)
                await self._send_sticker(parcel.user_id, result.carrier)
                await self._notify(
                    parcel.user_id, text, report,
                    silent=None if big_moment else True,
                    reply_markup=card_keyboard(current) if current is not None else None,
                )
```

```python
    async def _send_sticker(self, chat_id: int, carrier: str) -> None:
        if carrier in self._broken_stickers:
            return
        file_id = await self._repo.get_meta(f"sticker:{carrier}")
        if not file_id:
            return
        try:
            ok = await self._notifier.send_sticker(chat_id, file_id)
        except Exception:
            ok = False
        if not ok:
            self._broken_stickers.add(carrier)
            log.warning("carrier sticker failed carrier=%s", carrier)
```

`_notify(..., silent=None, reply_markup=None)` passes `reply_markup` to `send`. `digest.py`: `DigestNotifier.send` gains `reply_markup=None`; `send_all` computes the parcels through a private `_compose(user_id, cutoff) -> tuple[str, list[Parcel]] | None` shared with `build`, and passes `reply_markup=list_keyboard(list(enumerate(parcels, start=1)), page=1, pages=1)`.

- [ ] **Step 4: Green + gates + commit** `Poller: per-parcel check, sound on big moments, carrier stickers, card buttons`.

---

### Task 3: Callback handler, buttons on adds, paged /list, rename from a card

**Files:** Create `bot/handlers_callback.py`, `tests/test_callback_handler.py`; modify `bot/handlers_user.py`, `bot/app.py`, `tests/test_label_flow.py` (fake `reply_text` accepts `reply_markup`), `tests/test_photo_handler.py` if needed.

**Interfaces:**
- `handlers_user.reply(update, text, reply_markup=None) -> Message | None`; `handlers_user.drop_pending(context)` (renamed from `_drop_pending`); `PENDING_LABEL` dicts may carry `card: {"message_id": int, "page": int | None}`; after a label answer with `card`, the card message is re-rendered with `format_parcel_card` + `card_keyboard`.
- `handlers_callback.callback_query(update, context)` handles `p:<id>:<action>[:<page>]` (`card`, `his`, `chk`, `ren`, `del`, `dok`, `dno`, `shr`), `l:<page>` and `s:<token>:<ok|no>`; `CHECK_KEY = "parcel_checks"` in `bot_data` maps parcel id → last check time.
- `/list` replies page 1 with `list_keyboard`; add confirmations (`added`/`duplicate` with a parcel) carry `card_keyboard`.

- [ ] **Step 1: Tests** `tests/test_callback_handler.py` with a `FakeQuery` (`data`, `from_user`, `message` with `message_id` and `chat.id`, recording `answer(text=None, show_alert=False)` calls and `edit_message_text(text, **kwargs)` calls), a `FakeBot` (`id`, `username`, `send_message` returning an object with `message_id`, `delete_message`, `edit_message_text`), deps built like `tests/test_label_flow.py`. Tests:
  - `card` from a list edits to `format_parcel_card` with `card_keyboard(page=1)` (last row `l:1`).
  - `his` edits to the history text with `back_keyboard`.
  - another user's parcel id → one answer with `texts.CARD_NOT_FOUND`, no edit.
  - `chk` calls `poller.check_parcel` (fake carrier result "Đang giao hàng"), edits the card showing `95%`; a second tap within 5 minutes answers `texts.CHECK_TOO_SOON.format(minutes=5)` without checking.
  - `del` edits to `REMOVE_CONFIRM`; `dno` restores the card; `dok` removes the parcel and edits to `REMOVED` with no keyboard (with `list_back_keyboard(page)` when a page was given).
  - `ren` sends `LABEL_ASK`, then `text_message` with the name sets the label, edits the card message (bot `edit_message_text` with `card_keyboard`), and deletes the prompt and the answer.
  - `l:2` edits to page 2 of the list with `list_keyboard`.
  - `BadRequest("Message is not modified")` on edit is ignored (still one answer, no exception).
  - `/list` (via `list_cmd`) replies with a markup whose first button is `p:<id>:card:1`; an add via `text_message` replies with `card_keyboard` (first button `p:<id>:ren`).

- [ ] **Step 2: Red.**

- [ ] **Step 3: Implement** `bot/handlers_callback.py` (dispatcher `callback_query` → `_parcel_action`, `_list_page`, `_share_answer` (Task 4 fills `_share_answer`; until then it answers and returns)); `_edit(query, text, markup)` swallowing "not modified" `BadRequest` and logging other `TelegramError` types; `handlers_user` changes listed above; `app.py`: `app.add_handler(CallbackQueryHandler(callback_query))` after the message handlers.

- [ ] **Step 4: Green + gates + commit** `Parcel card buttons: history, check, remove, rename, paged list`.

---

### Task 4: Share links

**Files:** Create `services/sharing.py`, `tests/test_sharing.py`; modify `bot/handlers_callback.py` (`shr`, `_share_answer`), `bot/handlers_user.py` (`start` with `s_<token>`), `tests/test_callback_handler.py`.

**Interfaces:** `sharing.share_token(repo, parcel_id) -> str` (reuses a live token); `sharing.shared_parcel(repo, token) -> Parcel | None`; `SHARE_KEY = "share:"`, `SHARE_OF_KEY = "share-of:"`; token `secrets.token_urlsafe(9)`.

- [ ] **Step 1: Tests:** token reuse and lookup; `shr` edits to `SHARE_LINK` containing `https://t.me/<bot username>?start=s_<token>` with `back_keyboard`; `/start s_<token>` from another allowed user replies `SHARE_OPEN` (code blurred) with `share_open_keyboard`; `s:<token>:ok` adds the same tracking number and label to that user and edits to the add result with `card_keyboard`; `s:<token>:no` edits to `CANCELLED`; an unknown token replies/answers `SHARE_NOT_FOUND`; the sharer opening their own link gets their card.

- [ ] **Step 2: Red. Step 3: Implement. Step 4: Green + gates + commit** `Share a parcel with another allowed user by link`.

---

### Task 5: /sticker admin command

**Files:** modify `bot/handlers_admin.py`, `bot/app.py`, create `tests/test_sticker_cmd.py`.

**Interfaces:** `sticker_cmd` (admin only): no args → `STICKER_LIST`; `<carrier>` replying to a sticker → meta `sticker:<carrier>` = `file_id`, `STICKER_SET`; `<carrier> off` → `delete_meta`, `STICKER_REMOVED`; unknown carrier → `STICKER_UNKNOWN`; no replied sticker → `STICKER_USAGE`.

- [ ] **Step 1: Tests** for each branch (fake message with `reply_to_message.sticker.file_id = "file-test"`, non-admin refused by `admin_only`).
- [ ] **Step 2: Red. Step 3: Implement + register `CommandHandler("sticker", sticker_cmd, filters=private)`. Step 4: Green + gates + commit** `Admin maps carrier stickers with /sticker`.

---

### Task 6: Docs, restart, live check

- [ ] README: "Buttons" and "Carrier stickers" sections (how to map: send a sticker to the bot, reply `/sticker spx`), sound rule, share links. BUILD_PLAN 2.2 changes block, regenerate SPEC (version 2.2). Spec status line with commits.
- [ ] Safe restart; log shows `bot started`, no traceback; `/health` unaffected.
- [ ] Commit docs.
