import functools
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from telegram import Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import ApplicationHandlerStop, ContextTypes

from vn_parcel_bot import texts
from vn_parcel_bot.bot.deps import get_deps
from vn_parcel_bot.db.repo import User

Handler = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[Any]]


def is_authorized(user: User | None, telegram_id: int, admin_id: int) -> bool:
    return telegram_id == admin_id or (user is not None and user.is_allowed)


async def gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    chat = update.effective_chat
    if tg_user is None or chat is None or chat.type != ChatType.PRIVATE:
        raise ApplicationHandlerStop
    deps = get_deps(context)
    db_user = await deps.repo.get_user(tg_user.id)
    if not is_authorized(db_user, tg_user.id, deps.settings.admin_telegram_id):
        if update.effective_message is not None:
            await update.effective_message.reply_text(
                texts.NOT_ALLOWED.format(user_id=tg_user.id), parse_mode=ParseMode.HTML
            )
        raise ApplicationHandlerStop
    await deps.repo.upsert_user(tg_user.id, now=datetime.now(UTC), name=tg_user.full_name)


def admin_only(handler: Handler) -> Handler:
    @functools.wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
        admin_id = context.bot_data["settings"].admin_telegram_id
        if update.effective_user is None or update.effective_user.id != admin_id:
            if update.effective_message is not None:
                await update.effective_message.reply_text(
                    texts.ADMIN_ONLY, parse_mode=ParseMode.HTML
                )
            return None
        return await handler(update, context)

    return wrapper
