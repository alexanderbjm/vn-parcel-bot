from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from tests.fakes import FakeCarrier, FakeNotifier, fake_registry
from vn_parcel_bot import texts
from vn_parcel_bot.bot.deps import Deps
from vn_parcel_bot.bot.handlers_callback import callback_query
from vn_parcel_bot.bot.handlers_user import (
    PENDING_LABEL,
    PENDING_PHONE,
    PENDING_REMOVE,
    label_cmd,
    list_cmd,
    remove_cmd,
    text_message,
    track_cmd,
)
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.parcels import ParcelService
from vn_parcel_bot.services.poller import Poller

T0 = datetime(2026, 9, 1, 5, 0, tzinfo=UTC)
USER = 111
CHAT = 111
BOT_ID = 999
CODES = [f"SPXVN00000000000{index}" for index in range(1, 8)]
JT = "840000000001"


def blurred(code: str) -> str:
    return f'<span class="tg-spoiler">{code}</span>'


def items(*codes: str) -> str:
    return "\n".join(f"• <b>{blurred(code)}</b>" for code in codes)


class FakeBot:
    id = BOT_ID
    username = "vn_parcel_hozk_bot"

    def __init__(self):
        self.deleted: list[int] = []
        self.edited: list[tuple[int, str, object]] = []

    async def delete_message(self, chat_id, message_id):
        self.deleted.append(message_id)

    async def edit_message_text(self, text, chat_id=None, message_id=None, **kwargs):
        self.edited.append((message_id, text, kwargs.get("reply_markup")))


class ChatLog:
    def __init__(self):
        self.replies: list[SimpleNamespace] = []
        self.next_id = 500


class Msg:
    def __init__(self, log, message_id, text=None, reply_to=None, from_bot=False):
        self.log = log
        self.message_id = message_id
        self.text = text
        self.text_html = text
        self.caption = None
        self.reply_to_message = reply_to
        self.from_user = SimpleNamespace(id=BOT_ID if from_bot else USER)
        self.chat = SimpleNamespace(id=CHAT)

    async def reply_text(self, text, **kwargs):
        self.log.next_id += 1
        self.log.replies.append(
            SimpleNamespace(id=self.log.next_id, text=text, markup=kwargs.get("reply_markup"))
        )
        return SimpleNamespace(message_id=self.log.next_id)


class FakeQuery:
    def __init__(self, log, data, message_id):
        self.data = data
        self.from_user = SimpleNamespace(id=USER)
        self.message = Msg(log, message_id, from_bot=True)
        self.answers: list[str | None] = []
        self.edits: list[tuple[str, object]] = []

    async def answer(self, text=None, **kwargs):
        self.answers.append(text)

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs.get("reply_markup")))


@pytest.fixture
async def env(settings):
    repo = await Repository.open(":memory:")
    await repo.upsert_user(USER, now=T0, is_allowed=True, is_admin=True)
    registry = fake_registry({"spx": FakeCarrier("spx"), "jt": FakeCarrier("jt")})
    http = httpx.AsyncClient()
    parcels = ParcelService(repo, registry, http, settings, lambda: T0)
    poller = Poller(repo, registry, http, FakeNotifier(), settings, lambda: T0)
    deps = Deps(settings, repo, http, parcels, poller, FakeNotifier())
    context = SimpleNamespace(
        bot_data={"deps": deps, "settings": settings}, user_data={}, bot=FakeBot(), args=[]
    )
    user = await repo.get_user(USER)
    yield SimpleNamespace(deps=deps, repo=repo, context=context, log=ChatLog(), user=user)
    await http.aclose()
    await repo.close()


def update_for(message):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=USER, full_name="U", first_name="U"),
        effective_chat=SimpleNamespace(id=CHAT),
        effective_message=message,
    )


async def command(env, handler, message_id, text, args, reply_to=None):
    env.context.args = args
    message = Msg(env.log, message_id, text=text, reply_to=reply_to)
    await handler(update_for(message), env.context)
    return env.log.replies[-1]


async def answer(env, message_id, text):
    await text_message(update_for(Msg(env.log, message_id, text=text)), env.context)


async def tap(env, data, message_id):
    query = FakeQuery(env.log, data, message_id)
    update = update_for(query.message)
    update.callback_query = query
    await callback_query(update, env.context)
    return query


def buttons(markup):
    return [[button.callback_data for button in row] for row in markup.inline_keyboard]


async def add_all(env, count):
    for code in CODES[:count]:
        await env.deps.parcels.add(env.user, code)
    return await env.deps.parcels.list_for(USER)


async def codes_left(env):
    return [parcel.tracking_number for parcel in await env.deps.parcels.list_for(USER)]


# Removing


async def test_remove_asks_with_buttons_and_removes_on_confirm(env):
    parcels = await add_all(env, 1)
    prompt = await command(env, remove_cmd, 60, "/remove 1", ["1"])
    assert prompt.text == texts.REMOVE_CONFIRM.format(title=blurred(CODES[0]))
    assert buttons(prompt.markup) == [["rm:ok", "rm:no"]]
    query = await tap(env, "rm:ok", prompt.id)
    assert await env.repo.get_parcel(parcels[0].id) is None
    assert query.edits == [(texts.REMOVED.format(title=blurred(CODES[0])), None)]
    assert 60 in env.context.bot.deleted
    assert PENDING_REMOVE not in env.context.user_data


async def test_remove_cancel_button_keeps_the_parcel(env):
    parcels = await add_all(env, 1)
    prompt = await command(env, remove_cmd, 60, "/remove 1", ["1"])
    query = await tap(env, "rm:no", prompt.id)
    assert await env.repo.get_parcel(parcels[0].id) is not None
    assert query.edits == [(texts.CANCELLED, None)]
    assert 60 in env.context.bot.deleted
    assert PENDING_REMOVE not in env.context.user_data


async def test_typed_yes_no_longer_confirms(env):
    parcels = await add_all(env, 1)
    await command(env, remove_cmd, 60, "/remove 1", ["1"])
    await answer(env, 61, "có")
    assert await env.repo.get_parcel(parcels[0].id) is not None


async def test_remove_several_list_numbers_at_once(env):
    await add_all(env, 4)
    prompt = await command(env, remove_cmd, 60, "/remove 1, 3 3 9", ["1,", "3", "3", "9"])
    expected = texts.REMOVE_CONFIRM_MANY.format(count=2, items=items(CODES[0], CODES[2]))
    assert prompt.text == expected + texts.REMOVE_MISSING.format(refs="9")
    assert prompt.markup.inline_keyboard[0][0].text == texts.BTN_CONFIRM_REMOVE_MANY.format(count=2)
    query = await tap(env, "rm:ok", prompt.id)
    assert await codes_left(env) == [CODES[1], CODES[3]]
    assert query.edits[0][0] == texts.REMOVED_MANY.format(count=2, items=items(CODES[0], CODES[2]))


async def test_remove_by_code_still_works(env):
    await add_all(env, 2)
    prompt = await command(env, remove_cmd, 60, f"/remove {CODES[1]}", [CODES[1]])
    assert prompt.text == texts.REMOVE_CONFIRM.format(title=blurred(CODES[1]))
    await tap(env, "rm:ok", prompt.id)
    assert await codes_left(env) == [CODES[0]]


async def test_remove_with_nothing_found_asks_nothing(env):
    await add_all(env, 1)
    reply = await command(env, remove_cmd, 60, "/remove 9", ["9"])
    assert reply.text == texts.PARCEL_NOT_FOUND.format(ref="9")
    assert reply.markup is None
    assert PENDING_REMOVE not in env.context.user_data


async def test_stale_remove_button_is_refused(env):
    parcels = await add_all(env, 1)
    prompt = await command(env, remove_cmd, 60, "/remove 1", ["1"])
    stale = await tap(env, "rm:ok", prompt.id + 50)
    assert stale.answers == [texts.BUTTON_EXPIRED]
    assert await env.repo.get_parcel(parcels[0].id) is not None
    nothing = await tap(env, "rm:no", 999)
    assert nothing.answers == [texts.BUTTON_EXPIRED]


# Labels


async def test_label_prompt_offers_clear_and_cancel_buttons(env):
    await add_all(env, 1)
    await env.deps.parcels.rename(USER, CODES[0], "Tai nghe")
    prompt = await command(env, label_cmd, 60, f"/label {CODES[0]}", [CODES[0]])
    assert prompt.text == texts.LABEL_ASK.format(code=blurred(CODES[0]))
    assert buttons(prompt.markup) == [["lb:clr", "lb:no"]]
    await tap(env, "lb:clr", prompt.id)
    assert (await env.repo.find_parcel(USER, CODES[0])).label is None
    assert env.log.replies[-1].text == texts.LABEL_CLEARED.format(code=blurred(CODES[0]))
    assert sorted(env.context.bot.deleted) == sorted([60, prompt.id])
    assert PENDING_LABEL not in env.context.user_data


async def test_label_prompt_without_a_label_has_only_cancel(env):
    await add_all(env, 1)
    prompt = await command(env, label_cmd, 60, f"/label {CODES[0]}", [CODES[0]])
    assert buttons(prompt.markup) == [["lb:no"]]
    query = await tap(env, "lb:no", prompt.id)
    assert query.edits == [(texts.CANCELLED, None)]
    assert 60 in env.context.bot.deleted
    assert PENDING_LABEL not in env.context.user_data


async def test_typed_dash_is_just_a_name(env):
    await add_all(env, 1)
    await command(env, label_cmd, 60, f"/label {CODES[0]}", [CODES[0]])
    await answer(env, 61, "-")
    assert (await env.repo.find_parcel(USER, CODES[0])).label == "-"


async def test_reply_to_several_parcels_offers_a_picker(env):
    parcels = await add_all(env, 2)
    bot_message = Msg(env.log, 50, text=f"1. {CODES[0]}\n2. {CODES[1]}", from_bot=True)
    picker = await command(env, label_cmd, 60, "/label Tai nghe", ["Tai", "nghe"], bot_message)
    assert picker.text == texts.LABEL_PICK
    assert buttons(picker.markup) == [[f"lb:p:{parcels[0].id}"], [f"lb:p:{parcels[1].id}"]]
    assert picker.markup.inline_keyboard[1][0].text == "SPXVN…002"
    await tap(env, f"lb:p:{parcels[1].id}", picker.id)
    assert (await env.repo.find_parcel(USER, CODES[1])).label == "Tai nghe"
    assert (await env.repo.find_parcel(USER, CODES[0])).label is None
    assert sorted(env.context.bot.deleted) == sorted([60, picker.id])


async def test_picker_without_a_name_asks_for_one(env):
    parcels = await add_all(env, 2)
    bot_message = Msg(env.log, 50, text=f"1. {CODES[0]}\n2. {CODES[1]}", from_bot=True)
    picker = await command(env, label_cmd, 60, "/label", [], bot_message)
    query = await tap(env, f"lb:p:{parcels[0].id}", picker.id)
    assert query.edits[0][0] == texts.LABEL_ASK.format(code=blurred(CODES[0]))
    assert env.context.user_data[PENDING_LABEL]["prompt_id"] == picker.id
    await answer(env, 61, "Ốp")
    assert (await env.repo.find_parcel(USER, CODES[0])).label == "Ốp"


# Phone digits


async def test_phone_prompt_has_a_cancel_button(env):
    prompt = await command(env, track_cmd, 60, f"/track {JT}", [JT])
    assert buttons(prompt.markup) == [["ph:no"]]
    query = await tap(env, "ph:no", prompt.id)
    assert PENDING_PHONE not in env.context.user_data
    assert query.edits == [(texts.CANCELLED, None)]


# Choosing several parcels from /list


async def test_list_multi_select_removes_the_chosen_parcels(env):
    parcels = await add_all(env, 3)
    listed = await command(env, list_cmd, 60, "/list", [])
    assert buttons(listed.markup)[-2] == ["r:1", "m:on:1"]
    assert buttons(listed.markup)[-1] == ["so:n:1"]
    started = await tap(env, "m:on:1", listed.id)
    text, markup = started.edits[0]
    assert text.startswith(texts.SELECT_HEADER.format(count=0))
    assert buttons(markup)[0] == [f"m:t:{parcel.id}:1" for parcel in parcels]
    assert buttons(markup)[-1] == ["m:go:1", "m:off:1"]
    await tap(env, f"m:t:{parcels[0].id}:1", listed.id)
    toggled = await tap(env, f"m:t:{parcels[2].id}:1", listed.id)
    text, markup = toggled.edits[0]
    assert text.startswith(texts.SELECT_HEADER.format(count=2))
    assert [button.text for button in markup.inline_keyboard[0]] == ["☑ 1", "2", "☑ 3"]
    confirm = await tap(env, "m:go:1", listed.id)
    text, markup = confirm.edits[0]
    assert text == texts.REMOVE_CONFIRM_MANY.format(count=2, items=items(CODES[0], CODES[2]))
    assert buttons(markup) == [["rm:ok", "rm:no"]]
    done = await tap(env, "rm:ok", listed.id)
    assert await codes_left(env) == [CODES[1]]
    assert buttons(done.edits[0][1]) == [["l:1"]]


async def test_multi_select_needs_a_choice_and_can_be_left(env):
    await add_all(env, 2)
    listed = await command(env, list_cmd, 60, "/list", [])
    await tap(env, "m:on:1", listed.id)
    empty = await tap(env, "m:go:1", listed.id)
    assert empty.answers == [texts.SELECT_NONE]
    left = await tap(env, "m:off:1", listed.id)
    assert left.edits[0][0].startswith(texts.LIST_HEADER)
    assert buttons(left.edits[0][1])[-2] == ["r:1", "m:on:1"]
    assert await codes_left(env) == CODES[:2]


async def test_multi_select_pages_keep_the_selection(env):
    parcels = await add_all(env, 7)
    listed = await command(env, list_cmd, 60, "/list", [])
    await tap(env, "m:on:1", listed.id)
    await tap(env, f"m:t:{parcels[0].id}:1", listed.id)
    page_two = await tap(env, "m:pg:2", listed.id)
    text, markup = page_two.edits[0]
    assert text.startswith(texts.SELECT_HEADER.format(count=1))
    assert [button.text for button in markup.inline_keyboard[0]] == ["6", "7"]
    assert buttons(markup)[1] == ["m:pg:1", "m:pg:2", "m:pg:1"]


async def test_selection_on_another_message_is_stale(env):
    parcels = await add_all(env, 2)
    listed = await command(env, list_cmd, 60, "/list", [])
    await tap(env, "m:on:1", listed.id)
    stale = await tap(env, f"m:t:{parcels[0].id}:1", listed.id + 7)
    assert stale.answers == [texts.BUTTON_EXPIRED]
