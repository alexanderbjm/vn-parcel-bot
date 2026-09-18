import io
from types import SimpleNamespace

import pytest
from PIL import Image

from tests.fakes import FakeNotifier
from vn_parcel_bot import texts
from vn_parcel_bot.bot.handlers_admin import sticker_cmd
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.stickers import STICKER_STATUSES

ADMIN = 111


def photo_png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (600, 400), (90, 140, 200)).save(buffer, "PNG")
    return buffer.getvalue()


class FakeTelegramFile:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def download_as_bytearray(self) -> bytearray:
        return bytearray(self._data)


class FakeBot:
    """Only what /sticker needs: fetching a replied photo to stamp the status onto."""

    def __init__(self, data: bytes | None = None) -> None:
        self._data = data
        self.requested: list[str] = []

    async def get_file(self, file_id: str) -> FakeTelegramFile:
        self.requested.append(file_id)
        if self._data is None:
            raise RuntimeError("telegram said no")
        return FakeTelegramFile(self._data)


class Msg:
    def __init__(self, reply_to=None):
        self.reply_to_message = reply_to
        self.texts: list[str] = []

    async def reply_text(self, text, **kwargs):
        self.texts.append(text)


@pytest.fixture
async def env(settings):
    repo = await Repository.open(":memory:")
    notifier = FakeNotifier()
    deps = SimpleNamespace(repo=repo, settings=settings, notifier=notifier)
    yield SimpleNamespace(
        repo=repo, deps=deps, settings=settings, notifier=notifier, bot=FakeBot(photo_png())
    )
    await repo.close()


async def run(env, args, user_id=ADMIN, reply_to=None):
    message = Msg(reply_to)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_message=message,
        effective_chat=SimpleNamespace(id=user_id),
    )
    context = SimpleNamespace(
        args=args, bot_data={"deps": env.deps, "settings": env.settings}, bot=env.bot
    )
    await sticker_cmd(update, context)
    return message.texts


def sticker_message(file_id="file-test"):
    return SimpleNamespace(sticker=SimpleNamespace(file_id=file_id))


def photo_message():
    return SimpleNamespace(sticker=None, photo=[SimpleNamespace(file_id="file-photo")])


async def test_set_list_and_remove_sticker(env):
    assert await run(env, ["moving"], reply_to=sticker_message()) == [
        texts.STICKER_SET.format(status="moving")
    ]
    assert await env.repo.get_meta("sticker:moving") == "file-test"
    assert await run(env, []) == [texts.STICKER_LIST.format(statuses="moving (đang trên đường)")]
    assert await run(env, ["moving", "off"]) == [texts.STICKER_REMOVED.format(status="moving")]
    assert await env.repo.get_meta("sticker:moving") is None
    assert await run(env, []) == [texts.STICKER_LIST.format(statuses="—")]


async def test_a_replied_photo_becomes_that_statuses_cover(env):
    assert await run(env, ["delivered"], reply_to=photo_message()) == [
        texts.STICKER_COVER_SET.format(status="delivered")
    ]

    assert env.bot.requested == ["file-photo"]
    assert await env.repo.get_meta("sticker:delivered") == "file-uploaded"
    assert [chat_id for chat_id, _ in env.notifier.uploads] == [ADMIN], "uploaded to the admin"


async def test_a_photo_that_cannot_be_fetched_is_reported(env):
    env.bot._data = None

    assert await run(env, ["delivered"], reply_to=photo_message()) == [texts.STICKER_COVER_FAILED]
    assert await env.repo.get_meta("sticker:delivered") is None


async def test_a_carrier_code_is_not_a_status_any_more(env):
    # The stickers key on the delivery status now, so the old vocabulary is simply unknown.
    told = await run(env, ["spx"], reply_to=sticker_message())
    assert told == [texts.STICKER_UNKNOWN.format(statuses=", ".join(STICKER_STATUSES))]
    assert await env.repo.get_meta("sticker:spx") is None


async def test_sticker_usage(env):
    assert await run(env, ["delivered"]) == [texts.STICKER_USAGE]
    assert await run(env, ["delivered"], reply_to=SimpleNamespace(sticker=None, photo=None)) == [
        texts.STICKER_USAGE
    ]


async def test_sticker_is_admin_only(env):
    assert await run(env, ["moving"], user_id=222, reply_to=sticker_message()) == [texts.ADMIN_ONLY]
    assert await env.repo.get_meta("sticker:moving") is None
