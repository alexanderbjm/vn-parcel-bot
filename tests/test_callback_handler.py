from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from telegram.constants import ParseMode
from telegram.error import BadRequest

from tests.fakes import FakeCarrier, FakeNotifier, ev, fake_registry, found
from vn_parcel_bot import texts
from vn_parcel_bot.bot.deps import Deps
from vn_parcel_bot.bot.handlers_callback import callback_query
from vn_parcel_bot.bot.handlers_user import (
    PENDING_LABEL,
    check_cmd,
    list_cmd,
    start,
    text_message,
)
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.formatting import format_check_done, format_parcel_card
from vn_parcel_bot.services.parcels import ParcelService
from vn_parcel_bot.services.poller import Poller
from vn_parcel_bot.services.sharing import share_token
from vn_parcel_bot.tracking_codes import mask_code

T0 = datetime(2026, 9, 1, 5, 0, tzinfo=UTC)
USER = 111
ADMIN = 111
OTHER = 222
CHAT = 111
SPX = "SPXVN000000000001"
BLURRED = f'<span class="tg-spoiler">{SPX}</span>'
SHORT_BLURRED = f'<span class="tg-spoiler">{mask_code(SPX)}</span>'


class FakeBot:
    id = 999
    username = "vn_parcel_hozk_bot"

    def __init__(self):
        self.sent = []
        self.sent_kwargs = []
        self.deleted = []
        self.edited = []
        self.next_id = 900

    async def send_message(self, chat_id, text, **kwargs):
        self.next_id += 1
        self.sent.append((chat_id, text, kwargs.get("reply_markup")))
        self.sent_kwargs.append(kwargs)
        return SimpleNamespace(message_id=self.next_id)

    async def delete_message(self, chat_id, message_id):
        self.deleted.append(message_id)

    async def edit_message_text(self, text, chat_id=None, message_id=None, **kwargs):
        self.edited.append((message_id, text, kwargs.get("reply_markup")))


class FakeQuery:
    def __init__(self, data, user_id=USER, message_id=70, edit_error=None):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace(message_id=message_id, chat=SimpleNamespace(id=CHAT))
        self.answers = []
        self.edits = []
        self.edit_error = edit_error

    async def answer(self, text=None, show_alert=False, **kwargs):
        self.answers.append(text)

    async def edit_message_text(self, text, **kwargs):
        if self.edit_error is not None:
            raise self.edit_error
        self.edits.append((text, kwargs.get("reply_markup")))


class Msg:
    def __init__(self, message_id, text, sent):
        self.message_id = message_id
        self.text = text
        self.caption = None
        self.reply_to_message = None
        self.sent = sent

    async def reply_text(self, text, **kwargs):
        self.sent.append((text, kwargs.get("reply_markup")))
        return SimpleNamespace(message_id=800 + len(self.sent))


async def no_sleep(seconds):
    return None


@pytest.fixture
async def env(settings):
    repo = await Repository.open(":memory:")
    await repo.upsert_user(USER, now=T0, is_allowed=True, is_admin=True)
    await repo.upsert_user(OTHER, now=T0, is_allowed=True)
    fakes = {"spx": FakeCarrier("spx")}
    registry = fake_registry(fakes)
    http = httpx.AsyncClient()
    parcels = ParcelService(repo, registry, http, settings, lambda: T0)
    poller = Poller(
        repo, registry, http, FakeNotifier(), settings, lambda: T0, no_sleep, lambda: 0.0
    )
    deps = Deps(settings, repo, http, parcels, poller, FakeNotifier())
    bot = FakeBot()
    context = SimpleNamespace(
        bot_data={"deps": deps, "settings": settings}, user_data={}, bot=bot, args=[]
    )
    user = await repo.get_user(USER)
    yield SimpleNamespace(
        deps=deps, repo=repo, context=context, bot=bot, user=user, fakes=fakes, settings=settings
    )
    await http.aclose()
    await repo.close()


def query_update(query):
    return SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=query.from_user.id, full_name="U", first_name="U"),
        effective_chat=SimpleNamespace(id=CHAT),
        effective_message=query.message,
    )


def user_update(message):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=USER, full_name="U", first_name="U"),
        effective_chat=SimpleNamespace(id=CHAT),
        effective_message=message,
    )


async def tap(env, data, **kwargs):
    query = FakeQuery(data, **kwargs)
    await callback_query(query_update(query), env.context)
    return query


async def add_spx(env, code=SPX):
    return (await env.deps.parcels.add(env.user, code)).parcel


def first_data(markup):
    return markup.inline_keyboard[0][0].callback_data


def last_row_data(markup):
    return [button.callback_data for button in markup.inline_keyboard[-1]]


async def test_card_from_list_edits_to_card_with_back_row(env):
    parcel = await add_spx(env)
    query = await tap(env, f"p:{parcel.id}:card:1")
    text, markup = query.edits[0]
    assert text == format_parcel_card(await env.repo.get_parcel(parcel.id), env.settings.tz)
    assert last_row_data(markup) == ["l:1"]
    assert query.answers == [None]


async def test_history_edits_with_back_button(env):
    parcel = await add_spx(env)
    query = await tap(env, f"p:{parcel.id}:his")
    text, markup = query.edits[0]
    assert texts.HISTORY_EMPTY in text
    assert first_data(markup) == f"p:{parcel.id}:card"


async def test_other_users_parcel_is_refused(env):
    parcel = await add_spx(env)
    query = await tap(env, f"p:{parcel.id}:his", user_id=OTHER)
    assert query.answers == [texts.CARD_NOT_FOUND]
    assert query.edits == []


async def test_check_refreshes_card_and_has_cooldown(env):
    parcel = await add_spx(env)
    env.fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Đang giao hàng"))
    query = await tap(env, f"p:{parcel.id}:chk")
    assert "95%" in query.edits[0][0]
    again = await tap(env, f"p:{parcel.id}:chk")
    assert again.answers == [texts.CHECK_TOO_SOON.format(minutes=5)]
    assert again.edits == []


async def test_remove_confirm_cancel_and_remove(env):
    parcel = await add_spx(env)
    ask = await tap(env, f"p:{parcel.id}:del")
    assert ask.edits[0][0] == texts.REMOVE_CONFIRM.format(title=SHORT_BLURRED)
    assert first_data(ask.edits[0][1]) == f"p:{parcel.id}:dok"
    cancel = await tap(env, f"p:{parcel.id}:dno")
    assert first_data(cancel.edits[0][1]) == f"p:{parcel.id}:ren"
    confirm = await tap(env, f"p:{parcel.id}:dok:2")
    assert confirm.edits[0][0] == texts.REMOVED.format(title=SHORT_BLURRED)
    assert last_row_data(confirm.edits[0][1]) == ["l:2"]
    assert await env.repo.get_parcel(parcel.id) is None


async def test_removed_without_page_has_no_buttons(env):
    parcel = await add_spx(env)
    confirm = await tap(env, f"p:{parcel.id}:dok")
    assert confirm.edits[0][1] is None


async def test_rename_from_card_updates_card_and_cleans_up(env):
    parcel = await add_spx(env)
    await tap(env, f"p:{parcel.id}:ren", message_id=70)
    assert env.bot.sent[0][1] == texts.LABEL_ASK.format(code=BLURRED)
    prompt_id = env.context.user_data[PENDING_LABEL]["prompt_id"]
    await text_message(user_update(Msg(71, "Bàn chải", [])), env.context)
    assert (await env.repo.get_parcel(parcel.id)).label == "Bàn chải"
    edited_id, edited_text, markup = env.bot.edited[-1]
    assert edited_id == 70
    assert f"<b>Bàn chải · {SHORT_BLURRED}</b>" in edited_text
    assert first_data(markup) == f"p:{parcel.id}:ren"
    assert sorted(env.bot.deleted) == sorted([prompt_id, 71])


async def test_list_page_navigation(env):
    for index in range(1, 8):
        await add_spx(env, f"SPXVN00000000000{index}")
    query = await tap(env, "l:2")
    text, markup = query.edits[0]
    assert "6. " in text
    assert "Trang 2/2" in text
    assert markup.inline_keyboard[0][0].text == "6"
    assert [b.callback_data for b in markup.inline_keyboard[-2]] == ["l:1", "l:2", "l:1"]
    assert last_row_data(markup) == ["r:2", "m:on:2"]


async def test_not_modified_edit_is_ignored(env):
    parcel = await add_spx(env)
    error = BadRequest("Message is not modified: specified new message content is the same")
    query = await tap(env, f"p:{parcel.id}:card", edit_error=error)
    assert query.answers == [None]


async def test_list_command_and_add_reply_carry_buttons(env):
    added = []
    await text_message(user_update(Msg(60, SPX, added)), env.context)
    parcel = await env.repo.find_parcel(USER, SPX)
    assert first_data(added[-1][1]) == f"p:{parcel.id}:ren"
    listed = []
    await list_cmd(user_update(Msg(61, "/list", listed)), env.context)
    assert first_data(listed[-1][1]) == f"p:{parcel.id}:card:1"
    assert last_row_data(listed[-1][1]) == ["r:1", "m:on:1"]


def other_update(message):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=OTHER, full_name="O", first_name="O"),
        effective_chat=SimpleNamespace(id=OTHER),
        effective_message=message,
    )


async def test_share_button_shows_link(env):
    parcel = await add_spx(env)
    query = await tap(env, f"p:{parcel.id}:shr")
    text, markup = query.edits[0]
    assert "https://t.me/vn_parcel_hozk_bot?start=s_" in text
    assert first_data(markup) == f"p:{parcel.id}:card"


async def test_shared_link_lets_another_user_track(env):
    parcel = await add_spx(env)
    await env.deps.parcels.rename(USER, SPX, "Áo")
    token = await share_token(env.repo, parcel.id)
    env.context.args = [f"s_{token}"]
    opened = []
    await start(other_update(Msg(80, "/start", opened)), env.context)
    text, markup = opened[-1]
    assert text == texts.SHARE_OPEN.format(title=f"Áo · {SHORT_BLURRED}", carrier="SPX")
    assert [b.callback_data for b in markup.inline_keyboard[0]] == [
        f"s:{token}:ok",
        f"s:{token}:no",
    ]
    query = await tap(env, f"s:{token}:ok", user_id=OTHER)
    added = await env.repo.find_parcel(OTHER, SPX)
    assert added is not None
    assert added.label == "Áo"
    assert first_data(query.edits[0][1]) == f"p:{added.id}:ren"


async def test_shared_link_skip_and_unknown(env):
    parcel = await add_spx(env)
    token = await share_token(env.repo, parcel.id)
    skipped = await tap(env, f"s:{token}:no", user_id=OTHER)
    assert skipped.edits[0] == (texts.CANCELLED, None)
    assert await env.repo.find_parcel(OTHER, SPX) is None
    unknown = await tap(env, "s:missing00000:ok", user_id=OTHER)
    assert unknown.answers == [texts.SHARE_NOT_FOUND]
    env.context.args = ["s_missing00000"]
    replies = []
    await start(other_update(Msg(81, "/start", replies)), env.context)
    assert replies[-1][0] == texts.SHARE_NOT_FOUND


async def test_owner_opening_own_link_gets_card(env):
    parcel = await add_spx(env)
    token = await share_token(env.repo, parcel.id)
    env.context.args = [f"s_{token}"]
    replies = []
    await start(user_update(Msg(82, "/start", replies)), env.context)
    assert first_data(replies[-1][1]) == f"p:{parcel.id}:ren"


async def test_recheck_button_checks_all_and_redraws_the_list(env):
    parcel = await add_spx(env)
    env.fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Đang giao hàng"))
    query = await tap(env, "r:1")
    assert query.answers == [texts.CHECK_STARTED]
    text, markup = query.edits[0]
    assert text.startswith(format_check_done(1, 1, 0, rebuilt=1) + "\n\n")
    assert "📋" in text
    assert first_data(markup) == f"p:{parcel.id}:card:1"
    assert last_row_data(markup) == ["r:1", "m:on:1"]
    again = await tap(env, "r:1")
    assert again.answers == [texts.CHECK_TOO_SOON.format(minutes=2)]
    assert again.edits == []


async def test_recheck_matches_carriers_again(env):
    parcel = await env.repo.add_parcel(
        user_id=USER,
        carrier=None,
        candidates=("ninjavan",),
        tracking_number=SPX,
        phone_last4=None,
        now=T0,
        next_check_at=T0,
    )
    await env.repo.record_check_failure(parcel.id, next_check_at=T0, now=T0)
    assert await env.deps.parcels.redetect_carriers(USER) == 1
    changed = await env.repo.get_parcel(parcel.id)
    assert (changed.carrier, changed.candidates, changed.consecutive_failures) == (
        "spx",
        ("spx",),
        0,
    )
    assert await env.deps.parcels.redetect_carriers(USER) == 0


async def test_check_command_reports_redetected_parcels(env):
    await env.repo.add_parcel(
        user_id=USER,
        carrier=None,
        candidates=("ninjavan",),
        tracking_number=SPX,
        phone_last4=None,
        now=T0,
        next_check_at=T0,
    )
    replies = []
    await check_cmd(user_update(Msg(90, "/check", replies)), env.context)
    assert [text for text, _ in replies] == [texts.CHECK_STARTED, format_check_done(1, 0, 1)]
    assert texts.CHECK_REDETECTED.format(count=1) in replies[-1][0]
    await check_cmd(user_update(Msg(91, "/check", replies)), env.context)
    assert replies[-1][0] == texts.CHECK_TOO_SOON.format(minutes=2)


async def test_cmd_action_location_and_help(env):
    # Test cmd:loc triggers location prompt with HTML parse_mode
    query_loc = await tap(env, "cmd:loc")
    assert query_loc.answers == [None]
    assert any(texts.LOCATION_ASK in item[1] for item in env.bot.sent)
    assert any(kw.get("parse_mode") == ParseMode.HTML for kw in env.bot.sent_kwargs)
    assert env.context.user_data["pending_location"] == {"map_parcel": None}

    # When user already has home location saved
    await env.repo.set_home(USER, 21.03, 105.85)
    query_loc2 = await tap(env, "cmd:loc")
    assert query_loc2.answers == [None]
    assert any(texts.LOCATION_STATUS in item[1] for item in env.bot.sent)

    # Test cmd:help displays help with keyboard
    query_help = await tap(env, "cmd:help")
    assert query_help.answers == [None]
    assert query_help.edits[0][0].startswith("<b>📦 Hướng dẫn</b>")


async def test_adm_action_health_users_and_non_admin(env):
    # Non-admin gets rejected with alert
    non_admin_query = await tap(env, "adm:health", user_id=222)
    assert non_admin_query.answers == [texts.ADMIN_ONLY]

    # Admin gets health view
    admin_health = await tap(env, "adm:health", user_id=ADMIN)
    assert admin_health.answers == [None]
    assert "Tình trạng" in admin_health.edits[0][0]

    # Admin gets users view
    admin_users = await tap(env, "adm:users", user_id=ADMIN)
    assert admin_users.answers == [None]
    assert "Người dùng" in admin_users.edits[0][0]

    # Admin gets hozk menu
    admin_hozk = await tap(env, "adm:hozk", user_id=ADMIN)
    assert admin_hozk.answers == [None]
    assert texts.ADMIN_HELP in admin_hozk.edits[0][0]
