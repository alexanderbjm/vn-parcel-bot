import pytest
from telegram.constants import ParseMode
from telegram.error import Forbidden

from vn_parcel_bot.bot.notifier import TelegramNotifier


class FakeBot:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self.error = error

    async def send_message(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error


async def test_send_uses_html_silent_and_no_preview():
    bot = FakeBot()
    await TelegramNotifier(bot).send(5, "xin chào", silent=True)
    kwargs = bot.calls[0]
    assert (kwargs["chat_id"], kwargs["text"]) == (5, "xin chào")
    assert kwargs["parse_mode"] == ParseMode.HTML
    assert kwargs["disable_notification"] is True
    assert kwargs["link_preview_options"].is_disabled is True


async def test_forbidden_is_swallowed():
    await TelegramNotifier(FakeBot(Forbidden("blocked"))).send(5, "x")


async def test_other_errors_propagate():
    with pytest.raises(RuntimeError):
        await TelegramNotifier(FakeBot(RuntimeError("boom"))).send(5, "x")
