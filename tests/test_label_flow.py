from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from telegram.error import TelegramError

from tests.fakes import FakeCarrier, FakeNotifier, fake_registry
from vn_parcel_bot import texts
from vn_parcel_bot.bot.deps import Deps
from vn_parcel_bot.bot.handlers_user import (
    PENDING_LABEL,
    PENDING_PHONE,
    PENDING_REMOVE,
    cancel_cmd,
    label_cmd,
    remove_cmd,
    text_message,
    track_cmd,
)
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.parcels import ParcelService
from vn_parcel_bot.services.poller import Poller

T0 = datetime(2026, 9, 1, tzinfo=UTC)
USER = 111
CHAT = 111
BOT_ID = 999
SPX = "SPXVN000000000001"
SPX2 = "SPXVN000000000002"
JT = "840000000001"
BLURRED = f'<span class="tg-spoiler">{SPX}</span>'


class FakeBot:
    id = BOT_ID

    def __init__(self):
        self.fail_delete = False
        self.deleted: list[int] = []
        self.edited: list[tuple[int, str]] = []

    async def delete_message(self, chat_id, message_id):
        assert chat_id == CHAT
        if self.fail_delete:
            raise TelegramError("Message can't be deleted")
        self.deleted.append(message_id)

    async def edit_message_text(self, text, chat_id=None, message_id=None, **kwargs):
        assert chat_id == CHAT
        self.edited.append((message_id, text))


class Chat:
    def __init__(self):
        self.sent: list[str] = []
        self.last_id = 500

    def next_id(self):
        self.last_id += 1
        return self.last_id


class Msg:
    def __init__(self, chat, message_id, text=None, reply_to=None, from_bot=False):
        self.chat = chat
        self.message_id = message_id
        self.text = text
        self.text_html = text
        self.caption = None
        self.reply_to_message = reply_to
        self.from_user = SimpleNamespace(id=BOT_ID if from_bot else USER, is_bot=from_bot)

    async def reply_text(self, text, **kwargs):
        self.chat.sent.append(text)
        return SimpleNamespace(message_id=self.chat.next_id())


@pytest.fixture
async def env(settings):
    repo = await Repository.open(":memory:")
    await repo.upsert_user(USER, now=T0, is_allowed=True, is_admin=True)
    registry = fake_registry({"spx": FakeCarrier("spx"), "jt": FakeCarrier("jt")})
    http = httpx.AsyncClient()
    parcels = ParcelService(repo, registry, http, settings, lambda: T0)
    poller = Poller(repo, registry, http, FakeNotifier(), settings, lambda: T0)
    deps = Deps(settings, repo, http, parcels, poller, FakeNotifier())
    context = SimpleNamespace(bot_data={"deps": deps}, user_data={}, bot=FakeBot(), args=[])
    user = await repo.get_user(USER)
    yield SimpleNamespace(deps=deps, context=context, chat=Chat(), user=user, repo=repo)
    await http.aclose()
    await repo.close()


def update_for(message):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=USER, full_name="User", first_name="User"),
        effective_message=message,
        effective_chat=SimpleNamespace(id=CHAT),
    )


async def command(env, handler, message_id, text, args, reply_to=None):
    env.context.args = args
    await handler(update_for(Msg(env.chat, message_id, text=text, reply_to=reply_to)), env.context)


async def answer(env, message_id, text):
    await text_message(update_for(Msg(env.chat, message_id, text=text)), env.context)


async def label_of(env, code):
    return (await env.repo.find_parcel(USER, code)).label


async def test_reply_label_uses_parcel_in_bot_message_and_censors_it(env):
    await env.deps.parcels.add(env.user, SPX)
    bot_message = Msg(env.chat, 50, text=f"📦 <b>{SPX}</b> · SPX\n• 14/09 16:18", from_bot=True)
    await command(env, label_cmd, 60, "/label bàn chải điện", ["bàn", "chải", "điện"], bot_message)
    assert await label_of(env, SPX) == "bàn chải điện"
    assert env.context.bot.edited == [(50, f"📦 <b>{BLURRED}</b> · SPX\n• 14/09 16:18")]
    assert env.context.bot.deleted == [60]
    assert env.chat.sent[-1] == texts.LABEL_SET.format(label="bàn chải điện", code=BLURRED)


async def test_reply_label_matches_existing_name_without_editing(env):
    await env.deps.parcels.add(env.user, SPX)
    await env.deps.parcels.rename(USER, SPX, "Tai nghe")
    bot_message = Msg(env.chat, 50, text="📦 <b>Tai nghe</b> · SPX", from_bot=True)
    await command(env, label_cmd, 60, "/label Ốp lưng", ["Ốp", "lưng"], bot_message)
    assert await label_of(env, SPX) == "Ốp lưng"
    assert env.context.bot.edited == []
    assert env.context.bot.deleted == [60]


async def test_reply_to_users_own_message_is_not_edited(env):
    await env.deps.parcels.add(env.user, SPX)
    own_message = Msg(env.chat, 50, text=f"mã {SPX}")
    await command(env, label_cmd, 60, "/label Tai nghe", ["Tai", "nghe"], own_message)
    assert await label_of(env, SPX) == "Tai nghe"
    assert env.context.bot.edited == []
    assert env.context.bot.deleted == [60]


async def test_reply_to_a_message_with_several_parcels_is_ambiguous(env):
    await env.deps.parcels.add(env.user, SPX)
    await env.deps.parcels.add(env.user, SPX2)
    bot_message = Msg(env.chat, 50, text=f"1. {SPX}\n2. {SPX2}", from_bot=True)
    await command(env, label_cmd, 60, "/label Tai nghe", ["Tai", "nghe"], bot_message)
    assert env.chat.sent[-1] == texts.LABEL_AMBIGUOUS
    assert env.context.bot.deleted == []
    assert await label_of(env, SPX) is None


async def test_reply_to_a_message_without_parcels(env):
    bot_message = Msg(env.chat, 50, text="xin chào", from_bot=True)
    await command(env, label_cmd, 60, "/label Tai nghe", ["Tai", "nghe"], bot_message)
    assert env.chat.sent[-1] == texts.LABEL_REPLY_NOT_FOUND


async def test_label_with_code_blurs_confirmation_and_deletes_command(env):
    await env.deps.parcels.add(env.user, SPX)
    await command(env, label_cmd, 60, f"/label {SPX} Tai nghe", [SPX, "Tai", "nghe"])
    assert await label_of(env, SPX) == "Tai nghe"
    assert env.chat.sent[-1] == texts.LABEL_SET.format(label="Tai nghe", code=BLURRED)
    assert BLURRED in env.chat.sent[-1]
    assert env.context.bot.deleted == [60]


async def test_label_unknown_ref(env):
    await command(env, label_cmd, 60, "/label 9 Tai nghe", ["9", "Tai", "nghe"])
    assert env.chat.sent[-1] == texts.PARCEL_NOT_FOUND.format(ref="9")


async def test_label_without_name_asks_then_cleans_up(env):
    await env.deps.parcels.add(env.user, SPX)
    await command(env, label_cmd, 60, f"/label {SPX}", [SPX])
    assert env.chat.sent[-1] == texts.LABEL_ASK.format(code=BLURRED)
    prompt_id = env.context.user_data[PENDING_LABEL]["prompt_id"]
    await answer(env, 61, "Bàn chải")
    assert await label_of(env, SPX) == "Bàn chải"
    assert sorted(env.context.bot.deleted) == sorted([60, prompt_id, 61])
    assert PENDING_LABEL not in env.context.user_data
    assert env.chat.sent[-1] == texts.LABEL_SET.format(label="Bàn chải", code=BLURRED)


async def test_reply_label_without_name_censors_after_the_answer(env):
    await env.deps.parcels.add(env.user, SPX)
    bot_message = Msg(env.chat, 50, text=f"📦 {SPX} · SPX", from_bot=True)
    await command(env, label_cmd, 60, "/label", [], bot_message)
    assert env.context.bot.edited == []
    await answer(env, 61, "Tai nghe")
    assert await label_of(env, SPX) == "Tai nghe"
    assert env.context.bot.edited == [(50, f"📦 {BLURRED} · SPX")]


async def test_dash_clears_the_label(env):
    await env.deps.parcels.add(env.user, SPX)
    await env.deps.parcels.rename(USER, SPX, "Tai nghe")
    await command(env, label_cmd, 60, f"/label {SPX}", [SPX])
    await answer(env, 61, "-")
    assert await label_of(env, SPX) is None
    assert env.chat.sent[-1] == texts.LABEL_CLEARED.format(code=BLURRED)


async def test_remove_asks_for_confirmation_then_cleans_up(env):
    await env.deps.parcels.add(env.user, SPX)
    await command(env, remove_cmd, 60, "/remove 1", ["1"])
    assert env.chat.sent[-1] == texts.REMOVE_CONFIRM.format(title=BLURRED)
    assert await env.repo.find_parcel(USER, SPX) is not None
    prompt_id = env.context.user_data[PENDING_REMOVE]["prompt_id"]
    await answer(env, 61, "Có")
    assert await env.repo.find_parcel(USER, SPX) is None
    assert env.chat.sent[-1] == texts.REMOVED.format(title=BLURRED)
    assert sorted(env.context.bot.deleted) == sorted([60, prompt_id, 61])


async def test_remove_other_answer_cancels(env):
    await env.deps.parcels.add(env.user, SPX)
    await command(env, remove_cmd, 60, "/remove 1", ["1"])
    prompt_id = env.context.user_data[PENDING_REMOVE]["prompt_id"]
    await answer(env, 61, "không")
    assert await env.repo.find_parcel(USER, SPX) is not None
    assert env.chat.sent[-1] == texts.CANCELLED
    assert env.context.bot.deleted == [prompt_id]
    assert PENDING_REMOVE not in env.context.user_data


async def test_phone_prompt_and_digits_are_deleted_after_adding(env):
    await command(env, track_cmd, 60, f"/track {JT}", [JT])
    prompt_id = env.context.user_data[PENDING_PHONE]["prompt_id"]
    await answer(env, 61, "1234")
    assert (await env.repo.find_parcel(USER, JT)).phone_last4 == "1234"
    assert sorted(env.context.bot.deleted) == sorted([prompt_id, 61])


async def test_cancel_deletes_the_pending_prompt(env):
    await env.deps.parcels.add(env.user, SPX)
    await command(env, label_cmd, 60, f"/label {SPX}", [SPX])
    prompt_id = env.context.user_data[PENDING_LABEL]["prompt_id"]
    await command(env, cancel_cmd, 62, "/cancel", [])
    assert PENDING_LABEL not in env.context.user_data
    assert env.chat.sent[-1] == texts.CANCELLED
    assert sorted(env.context.bot.deleted) == sorted([prompt_id, 62])


async def test_delete_failures_do_not_break_labelling(env):
    env.context.bot.fail_delete = True
    await env.deps.parcels.add(env.user, SPX)
    await command(env, label_cmd, 60, f"/label {SPX} Tai nghe", [SPX, "Tai", "nghe"])
    assert await label_of(env, SPX) == "Tai nghe"
    assert env.chat.sent[-1] == texts.LABEL_SET.format(label="Tai nghe", code=BLURRED)


async def test_reply_label_leaves_an_already_blurred_message_alone(env):
    await env.deps.parcels.add(env.user, SPX)
    bot_message = Msg(env.chat, 50, text=f"📦 <b>{BLURRED}</b> · SPX", from_bot=True)
    await command(env, label_cmd, 60, "/label Tai nghe", ["Tai", "nghe"], bot_message)
    assert await label_of(env, SPX) == "Tai nghe"
    assert env.context.bot.edited == []
    assert env.chat.sent[-1] == texts.LABEL_SET.format(label="Tai nghe", code=BLURRED)
