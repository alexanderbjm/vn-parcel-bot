import asyncio
import logging
import warnings
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from telegram import Bot, LinkPreviewOptions
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, RetryAfter
from telegram.warnings import PTBDeprecationWarning

log = logging.getLogger(__name__)

MAX_RETRY_WAIT_SECONDS = 60


def _retry_seconds(exc: RetryAfter) -> float:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PTBDeprecationWarning)
        value = exc.retry_after
    return value.total_seconds() if isinstance(value, timedelta) else float(value)


class TelegramNotifier:
    def __init__(self, bot: Bot, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        self._bot = bot
        self._sleep = sleep

    async def _with_retry(self, call: Callable[[], Awaitable[Any]]) -> None:
        try:
            await call()
        except RetryAfter as exc:
            await self._sleep(min(_retry_seconds(exc), MAX_RETRY_WAIT_SECONDS))
            await call()

    async def send(
        self, chat_id: int, text: str, *, silent: bool = False, reply_markup: Any = None
    ) -> None:
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
                lambda: self._bot.send_sticker(
                    chat_id=chat_id, sticker=file_id, disable_notification=True
                )
            )
        except Forbidden:
            log.info("user %s blocked the bot", chat_id)
        except BadRequest:
            return False
        return True
