import json
import logging
import re
from datetime import UTC, datetime
from html import escape

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from vn_parcel_bot import texts
from vn_parcel_bot.bot.auth import admin_only
from vn_parcel_bot.bot.deps import get_deps
from vn_parcel_bot.bot.handlers_user import reply
from vn_parcel_bot.build_info import deployed_revision_async
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.keyboards import admin_keyboard, admin_sub_keyboard
from vn_parcel_bot.services.formatting import format_health, format_users
from vn_parcel_bot.services.stickers import (
    MANUAL_KEY,
    SHIPPED_KEY,
    STICKER_STATUSES,
    sticker_for,
)

log = logging.getLogger(__name__)

_USER_ID = re.compile(r"[1-9]\d*", re.ASCII)


def _target_id(args: list[str]) -> int | None:
    if not args or not _USER_ID.fullmatch(args[0]):
        return None
    return int(args[0])


@admin_only
async def allow_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = list(context.args or [])
    target = _target_id(args)
    if target is None:
        await reply(update, texts.USAGE_ALLOW)
        return
    deps = get_deps(context)
    name = " ".join(args[1:]).strip() or None
    await deps.repo.upsert_user(target, now=datetime.now(UTC), name=name, is_allowed=True)
    suffix = f" ({escape(name)})" if name else ""
    await reply(update, texts.ALLOWED.format(user_id=target, name_suffix=suffix))
    try:
        await context.bot.send_message(target, texts.ALLOWED_NOTICE, parse_mode=ParseMode.HTML)
    except TelegramError:
        log.info("could not notify newly allowed user %s", target)


@admin_only
async def revoke_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    target = _target_id(list(context.args or []))
    if target is None:
        await reply(update, texts.USAGE_REVOKE)
        return
    deps = get_deps(context)
    if target == deps.settings.admin_telegram_id:
        await reply(update, texts.CANNOT_REVOKE_ADMIN)
        return
    await deps.repo.upsert_user(target, now=datetime.now(UTC), is_allowed=False)
    await reply(update, texts.REVOKED.format(user_id=target))


@admin_only
async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = get_deps(context)
    users = await deps.repo.list_users()
    counts = {
        user.telegram_id: await deps.repo.count_active_parcels(user.telegram_id) for user in users
    }
    await reply(
        update,
        format_users(users, counts, deps.settings.admin_telegram_id),
        reply_markup=admin_sub_keyboard(),
    )


@admin_only
async def health_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = get_deps(context)
    last_poll = await deps.repo.get_meta("last_poll_at")
    report = await deps.repo.get_meta("last_poll_report")
    await reply(
        update,
        format_health(
            datetime.fromisoformat(last_poll) if last_poll else None,
            json.loads(report) if report else None,
            await deps.repo.count_all_active(),
            len(await deps.repo.list_users()),
            deps.settings.tz,
            await deployed_revision_async(),
        ),
        reply_markup=admin_sub_keyboard(),
    )


@admin_only
async def sticker_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = get_deps(context)
    args = [arg.casefold() for arg in (context.args or [])]
    if not args:
        await reply(
            update,
            texts.STICKER_LIST.format(statuses=await sticker_statuses_line(deps.repo) or "—"),
            reply_markup=admin_sub_keyboard(),
        )
        return
    status = args[0]
    if status not in STICKER_STATUSES:
        await reply(update, texts.STICKER_UNKNOWN.format(statuses=", ".join(STICKER_STATUSES)))
        return
    if len(args) > 1 and args[1] == "off":
        await deps.repo.delete_meta(f"{MANUAL_KEY}{status}")
        # A status with a shipped sticker still sends one; only the admin's own choice is gone.
        shipped = await deps.repo.get_meta(f"{SHIPPED_KEY}{status}")
        told = texts.STICKER_REMOVED_SHIPPED if shipped else texts.STICKER_REMOVED
        await reply(update, told.format(status=status))
        return
    replied = getattr(update.effective_message, "reply_to_message", None)
    sticker = getattr(replied, "sticker", None)
    if sticker is None:
        await reply(update, texts.STICKER_USAGE)
        return
    await deps.repo.set_meta(f"{MANUAL_KEY}{status}", sticker.file_id)
    await reply(update, texts.STICKER_SET.format(status=status))


async def sticker_statuses_line(repo: Repository) -> str:
    """The statuses that would send a sticker, each with what it means, as one line."""
    listed = []
    for status in STICKER_STATUSES:
        if await sticker_for(repo, status):
            listed.append(f"{status} ({texts.STICKER_STATUS_TEXT[status]})")
    return ", ".join(listed)


@admin_only
async def hozk_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply(update, texts.ADMIN_HELP, reply_markup=admin_keyboard())
