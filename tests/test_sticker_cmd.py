from types import SimpleNamespace

import pytest

from vn_parcel_bot import texts
from vn_parcel_bot.bot.handlers_admin import sticker_cmd
from vn_parcel_bot.db.repo import Repository

ADMIN = 111


class Msg:
    def __init__(self, reply_to=None):
        self.reply_to_message = reply_to
        self.texts: list[str] = []

    async def reply_text(self, text, **kwargs):
        self.texts.append(text)


@pytest.fixture
async def env(settings):
    repo = await Repository.open(":memory:")
    deps = SimpleNamespace(repo=repo, settings=settings, registry=None)
    yield SimpleNamespace(repo=repo, deps=deps, settings=settings)
    await repo.close()


async def run(env, args, user_id=ADMIN, reply_to=None):
    message = Msg(reply_to)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_message=message,
        effective_chat=SimpleNamespace(id=user_id),
    )
    context = SimpleNamespace(args=args, bot_data={"deps": env.deps, "settings": env.settings})
    await sticker_cmd(update, context)
    return message.texts


def sticker_message(file_id="file-test"):
    return SimpleNamespace(sticker=SimpleNamespace(file_id=file_id))


async def test_set_list_and_remove_sticker(env):
    assert await run(env, ["spx"], reply_to=sticker_message()) == [
        texts.STICKER_SET.format(carrier="SPX")
    ]
    assert await env.repo.get_meta("sticker:spx") == "file-test"
    assert await run(env, []) == [texts.STICKER_LIST.format(carriers="SPX")]
    assert await run(env, ["SPX", "off"]) == [texts.STICKER_REMOVED.format(carrier="SPX")]
    assert await env.repo.get_meta("sticker:spx") is None
    assert await run(env, []) == [texts.STICKER_LIST.format(carriers="—")]


async def test_sticker_usage_and_unknown_carrier(env):
    assert await run(env, ["spx"]) == [texts.STICKER_USAGE]
    assert await run(env, ["spx"], reply_to=SimpleNamespace(sticker=None)) == [texts.STICKER_USAGE]
    unknown = await run(env, ["dhl"], reply_to=sticker_message())
    assert unknown[0].startswith("Không có hãng này.")
    assert "spx" in unknown[0]
    assert await env.repo.get_meta("sticker:dhl") is None


async def test_sticker_is_admin_only(env):
    assert await run(env, ["spx"], user_id=222, reply_to=sticker_message()) == [texts.ADMIN_ONLY]
    assert await env.repo.get_meta("sticker:spx") is None
