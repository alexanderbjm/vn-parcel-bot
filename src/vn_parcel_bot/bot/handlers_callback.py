import logging
import math
from datetime import UTC, datetime
from html import escape

from telegram import CallbackQuery, InlineKeyboardMarkup, LinkPreviewOptions, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import ContextTypes

from vn_parcel_bot import texts
from vn_parcel_bot.bot.deps import get_deps
from vn_parcel_bot.bot.handlers_user import PENDING_LABEL, drop_pending, user_data
from vn_parcel_bot.constants import CHECK_COOLDOWN, MAX_EVENTS_IN_HISTORY
from vn_parcel_bot.db.repo import Parcel
from vn_parcel_bot.keyboards import (
    back_keyboard,
    card_keyboard,
    confirm_remove_keyboard,
    list_back_keyboard,
    list_keyboard,
)
from vn_parcel_bot.services.formatting import (
    format_history,
    format_parcel_card,
    format_parcel_list,
    list_page_items,
    masked_title,
)
from vn_parcel_bot.tracking_codes import mask_code

log = logging.getLogger(__name__)

CHECK_KEY = "parcel_checks"


async def _edit(query: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None) -> None:
    try:
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            log.info("callback edit failed type=%s", type(exc).__name__)
    except TelegramError as exc:
        log.info("callback edit failed type=%s", type(exc).__name__)


def _page(value: str | None) -> int | None:
    return int(value) if value is not None and value.isdigit() else None


async def callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data:
        return
    kind, _, rest = query.data.partition(":")
    parts = rest.split(":") if rest else []
    if kind == "p":
        await _parcel_action(context, query, parts)
    elif kind == "l":
        await _list_page(context, query, parts)
    else:
        await query.answer()


async def _parcel_action(
    context: ContextTypes.DEFAULT_TYPE, query: CallbackQuery, parts: list[str]
) -> None:
    if len(parts) < 2 or not parts[0].isdigit():
        await query.answer()
        return
    parcel_id, action = int(parts[0]), parts[1]
    page = _page(parts[2]) if len(parts) > 2 else None
    deps = get_deps(context)
    user_id = query.from_user.id
    parcel = await deps.repo.get_parcel(parcel_id)
    if parcel is None or parcel.user_id != user_id:
        await query.answer(texts.CARD_NOT_FOUND)
        return
    tz = deps.settings.tz
    if action in ("card", "dno"):
        await query.answer()
        await _edit(query, format_parcel_card(parcel, tz), card_keyboard(parcel, page=page))
    elif action == "his":
        await query.answer()
        events = await deps.repo.list_events(parcel.id, MAX_EVENTS_IN_HISTORY)
        await _edit(query, format_history(parcel, events, tz), back_keyboard(parcel.id, page))
    elif action == "chk":
        await _check(context, query, parcel, page)
    elif action == "ren":
        await query.answer()
        await _ask_rename(context, query, parcel, page)
    elif action == "del":
        await query.answer()
        await _edit(
            query,
            texts.REMOVE_CONFIRM.format(title=masked_title(parcel)),
            confirm_remove_keyboard(parcel.id, page),
        )
    elif action == "dok":
        await query.answer()
        await deps.parcels.remove(user_id, parcel.tracking_number)
        await _edit(
            query,
            texts.REMOVED.format(title=masked_title(parcel)),
            list_back_keyboard(page) if page is not None else None,
        )
    else:
        await query.answer()


async def _check(
    context: ContextTypes.DEFAULT_TYPE, query: CallbackQuery, parcel: Parcel, page: int | None
) -> None:
    checks: dict[int, datetime] = context.bot_data.setdefault(CHECK_KEY, {})
    now = datetime.now(UTC)
    last = checks.get(parcel.id)
    if last is not None and now - last < CHECK_COOLDOWN:
        remaining = (CHECK_COOLDOWN - (now - last)).total_seconds()
        await query.answer(texts.CHECK_TOO_SOON.format(minutes=math.ceil(remaining / 60)))
        return
    checks[parcel.id] = now
    await query.answer(texts.CHECK_STARTED)
    deps = get_deps(context)
    fresh = await deps.poller.check_parcel(parcel.user_id, parcel.id) or parcel
    await _edit(query, format_parcel_card(fresh, deps.settings.tz), card_keyboard(fresh, page=page))


async def _ask_rename(
    context: ContextTypes.DEFAULT_TYPE, query: CallbackQuery, parcel: Parcel, page: int | None
) -> None:
    drop_pending(context)
    message = query.message
    if message is None:
        return
    try:
        prompt = await context.bot.send_message(
            message.chat.id,
            texts.LABEL_ASK.format(code=escape(mask_code(parcel.tracking_number))),
            parse_mode=ParseMode.HTML,
        )
    except TelegramError as exc:
        log.info("rename prompt failed type=%s", type(exc).__name__)
        return
    user_data(context)[PENDING_LABEL] = {
        "code": parcel.tracking_number,
        "censor": None,
        "command_id": None,
        "prompt_id": prompt.message_id,
        "card": {"message_id": message.message_id, "page": page},
    }


async def _list_page(
    context: ContextTypes.DEFAULT_TYPE, query: CallbackQuery, parts: list[str]
) -> None:
    await query.answer()
    requested = (_page(parts[0]) if parts else None) or 1
    deps = get_deps(context)
    parcels = await deps.parcels.list_for(query.from_user.id)
    page, pages, numbered = list_page_items(parcels, requested)
    await _edit(
        query,
        format_parcel_list(parcels, deps.settings.tz, page=page),
        list_keyboard(numbered, page, pages),
    )
