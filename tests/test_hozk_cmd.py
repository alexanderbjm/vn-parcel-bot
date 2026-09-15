from types import SimpleNamespace

from vn_parcel_bot import texts
from vn_parcel_bot.bot.handlers_admin import hozk_cmd

ADMIN = 111


class Msg:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def reply_text(self, text, **kwargs):
        self.texts.append(text)


async def run(settings, user_id):
    message = Msg()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_message=message,
        effective_chat=SimpleNamespace(id=user_id),
    )
    deps = SimpleNamespace(settings=settings)
    context = SimpleNamespace(args=[], bot_data={"deps": deps, "settings": settings})
    await hozk_cmd(update, context)
    return message.texts


async def test_hozk_lists_admin_commands(settings):
    assert await run(settings, ADMIN) == [texts.ADMIN_HELP]
    for command in ("/users", "/allow", "/revoke", "/health", "/sticker", "/check"):
        assert command in texts.ADMIN_HELP


async def test_hozk_is_admin_only(settings):
    assert await run(settings, 222) == [texts.ADMIN_ONLY]
