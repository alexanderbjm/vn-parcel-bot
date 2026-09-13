from datetime import UTC, datetime
from types import SimpleNamespace

from vn_parcel_bot import texts
from vn_parcel_bot.bot.auth import admin_only, is_authorized
from vn_parcel_bot.db.repo import User

T0 = datetime(2026, 9, 1, tzinfo=UTC)


class MessageRecorder:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def reply_text(self, text, **kwargs):
        self.texts.append(text)


def member(allowed: bool) -> User:
    return User(5, "A", None, False, allowed, T0)


def test_is_authorized_matrix():
    assert is_authorized(None, 111, 111)
    assert is_authorized(member(True), 5, 111)
    assert not is_authorized(member(False), 5, 111)
    assert not is_authorized(None, 5, 111)


def fake_update(user_id: int, message: MessageRecorder):
    return SimpleNamespace(effective_user=SimpleNamespace(id=user_id), effective_message=message)


async def test_admin_only_blocks_non_admin(settings):
    called = []

    @admin_only
    async def handler(update, context):
        called.append(True)

    message = MessageRecorder()
    await handler(fake_update(2, message), SimpleNamespace(bot_data={"settings": settings}))
    assert called == []
    assert message.texts == [texts.ADMIN_ONLY]


async def test_admin_only_allows_admin(settings):
    called = []

    @admin_only
    async def handler(update, context):
        called.append(True)

    message = MessageRecorder()
    await handler(
        fake_update(settings.admin_telegram_id, message),
        SimpleNamespace(bot_data={"settings": settings}),
    )
    assert called == [True]
    assert message.texts == []
