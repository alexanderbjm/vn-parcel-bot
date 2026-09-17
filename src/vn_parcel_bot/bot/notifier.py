import asyncio
import logging
import warnings
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from telegram import Bot, LinkPreviewOptions
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, RetryAfter, TelegramError
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

    async def send_photo(
        self, chat_id: int, photo: bytes, caption: str, *, silent: bool = False
    ) -> None:
        try:
            await self._with_retry(
                lambda: self._bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    disable_notification=silent,
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

    async def upload_sticker(self, chat_id: int, image: bytes) -> str | None:
        """Send a sticker that belongs to no pack to learn its file_id, then take it back.

        Telegram lets a bot upload a .webp as a sticker, but the file_id — the cheap way to
        send it again — only exists once it has been sent. The message is deleted straight
        away, so the only trace left is the id.
        """
        try:
            message = await self._bot.send_sticker(
                chat_id=chat_id, sticker=image, disable_notification=True
            )
        except Forbidden:
            log.info("user %s blocked the bot", chat_id)
            return None
        except TelegramError:
            return None
        sticker = message.sticker
        try:
            await self._bot.delete_message(chat_id=chat_id, message_id=message.message_id)
        except TelegramError:
            log.info("could not remove the uploaded sticker message")
        return sticker.file_id if sticker is not None else None
