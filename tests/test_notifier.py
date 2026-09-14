import pytest
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, RetryAfter

from vn_parcel_bot.bot.notifier import TelegramNotifier


class FakeBot:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self.error = error
        self.stickers: list[dict] = []
        self.sticker_error: Exception | None = None

    async def send_message(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error

    async def send_sticker(self, **kwargs):
        self.stickers.append(kwargs)
        if self.sticker_error is not None:
            raise self.sticker_error


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


async def test_send_passes_reply_markup():
    bot = FakeBot()
    marker = object()
    await TelegramNotifier(bot).send(5, "x", reply_markup=marker)
    assert bot.calls[0]["reply_markup"] is marker


@pytest.mark.filterwarnings("ignore::telegram.warnings.PTBDeprecationWarning")
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
