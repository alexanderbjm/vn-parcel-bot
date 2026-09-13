import logging

from telegram import Bot, LinkPreviewOptions
from telegram.constants import ParseMode
from telegram.error import Forbidden

log = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send(self, chat_id: int, text: str, *, silent: bool = False) -> None:
        try:
            await self._bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_notification=silent,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        except Forbidden:
            log.info("user %s blocked the bot", chat_id)
