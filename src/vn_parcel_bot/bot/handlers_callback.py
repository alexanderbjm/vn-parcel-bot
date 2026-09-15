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
from vn_parcel_bot.bot.handlers_user import (
    PENDING_LABEL,
    PENDING_LABEL_PICK,
    PENDING_PHONE,
    PENDING_REMOVE,
    SELECTION,
    apply_label,
    card_markup,
    claim_recheck,
    current_user,
    delete_messages,
    drop_pending,
    recheck_all,
    user_data,
)
from vn_parcel_bot.constants import CHECK_COOLDOWN, MAX_EVENTS_IN_HISTORY
from vn_parcel_bot.db.repo import Parcel
from vn_parcel_bot.keyboards import (
    back_keyboard,
    card_keyboard,
    confirm_remove_keyboard,
    label_prompt_keyboard,
    list_back_keyboard,
    list_keyboard,
    remove_confirm_keyboard,
    select_keyboard,
)
from vn_parcel_bot.services.formatting import (
    format_add_outcome,
    format_history,
    format_parcel_card,
    format_parcel_list,
    format_remove_confirm,
    format_removed,
    list_page_items,
    parcel_title,
    spoiler,
)
from vn_parcel_bot.services.sharing import share_token, shared_parcel

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


def _message_id(query: CallbackQuery) -> int | None:
    return query.message.message_id if query.message is not None else None


def _chat_id(query: CallbackQuery) -> int | None:
    return query.message.chat.id if query.message is not None else None


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
    elif kind == "r":
        await _recheck(context, query, parts)
    elif kind == "s":
        await _share_answer(update, context, query, parts)
    elif kind == "rm":
        await _remove_answer(context, query, parts)
    elif kind == "lb":
        await _label_answer(update, context, query, parts)
    elif kind == "ph":
        await _phone_answer(context, query)
    elif kind == "m":
        await _select_action(context, query, parts)
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
            texts.REMOVE_CONFIRM.format(title=parcel_title(parcel)),
            confirm_remove_keyboard(parcel.id, page),
        )
    elif action == "shr":
        await query.answer()
        token = await share_token(deps.repo, parcel.id)
        link = f"https://t.me/{context.bot.username}?start=s_{token}"
        await _edit(
            query,
            texts.SHARE_LINK.format(title=parcel_title(parcel), link=escape(link)),
            back_keyboard(parcel.id, page),
        )
    elif action == "dok":
        await query.answer()
        await deps.parcels.remove(user_id, parcel.tracking_number)
        await _edit(
            query,
            texts.REMOVED.format(title=parcel_title(parcel)),
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
            texts.LABEL_ASK.format(code=spoiler(parcel.tracking_number)),
            parse_mode=ParseMode.HTML,
            reply_markup=label_prompt_keyboard(bool(parcel.label)),
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


async def _show_list(context: ContextTypes.DEFAULT_TYPE, query: CallbackQuery, page: int) -> None:
    deps = get_deps(context)
    parcels = await deps.parcels.list_for(query.from_user.id)
    page, pages, numbered = list_page_items(parcels, page)
    await _edit(
        query,
        format_parcel_list(parcels, deps.settings.tz, page=page),
        list_keyboard(numbered, page, pages, recheck=True),
    )


async def _list_page(
    context: ContextTypes.DEFAULT_TYPE, query: CallbackQuery, parts: list[str]
) -> None:
    await query.answer()
    await _show_list(context, query, (_page(parts[0]) if parts else None) or 1)


async def _recheck(
    context: ContextTypes.DEFAULT_TYPE, query: CallbackQuery, parts: list[str]
) -> None:
    user_id = query.from_user.id
    wait = claim_recheck(context, user_id)
    if wait is not None:
        await query.answer(texts.CHECK_TOO_SOON.format(minutes=wait))
        return
    await query.answer(texts.CHECK_STARTED)
    deps = get_deps(context)
    summary = await recheck_all(deps, user_id)
    parcels = await deps.parcels.list_for(user_id)
    requested = (_page(parts[0]) if parts else None) or 1
    page, pages, numbered = list_page_items(parcels, requested)
    await _edit(
        query,
        summary + "\n\n" + format_parcel_list(parcels, deps.settings.tz, page=page),
        list_keyboard(numbered, page, pages, recheck=True),
    )


def _pending_for(context: ContextTypes.DEFAULT_TYPE, key: str, query: CallbackQuery) -> dict | None:
    """The pending prompt behind this button, if the button belongs to it."""
    pending = user_data(context).get(key)
    if not isinstance(pending, dict) or pending.get("prompt_id") != _message_id(query):
        return None
    return pending


async def _remove_answer(
    context: ContextTypes.DEFAULT_TYPE, query: CallbackQuery, parts: list[str]
) -> None:
    pending = _pending_for(context, PENDING_REMOVE, query)
    if pending is None:
        await query.answer(texts.BUTTON_EXPIRED)
        return
    user_data(context).pop(PENDING_REMOVE, None)
    await query.answer()
    list_page = pending.get("list_page")
    back = list_back_keyboard(list_page) if list_page is not None else None
    if parts[:1] == ["ok"]:
        removed = await get_deps(context).parcels.remove_ids(query.from_user.id, pending["ids"])
        await _edit(query, format_removed(removed) if removed else texts.CARD_NOT_FOUND, back)
    else:
        await _edit(query, texts.CANCELLED, back)
    await delete_messages(context, _chat_id(query), [pending.get("command_id")])


async def _label_answer(
    update: Update, context: ContextTypes.DEFAULT_TYPE, query: CallbackQuery, parts: list[str]
) -> None:
    action = parts[0] if parts else ""
    deps = get_deps(context)
    if action == "p":
        await _label_pick(update, context, query, parts)
        return
    pending = _pending_for(context, PENDING_LABEL, query)
    if pending is None:
        await query.answer(texts.BUTTON_EXPIRED)
        return
    user_data(context).pop(PENDING_LABEL, None)
    await query.answer()
    if action == "clr":
        user = await current_user(update, deps)
        await apply_label(
            update,
            context,
            user,
            pending["code"],
            None,
            pending.get("censor"),
            [pending.get("command_id"), pending.get("prompt_id")],
            card=pending.get("card"),
        )
        return
    await _edit(query, texts.CANCELLED, None)
    await delete_messages(context, _chat_id(query), [pending.get("command_id")])


async def _label_pick(
    update: Update, context: ContextTypes.DEFAULT_TYPE, query: CallbackQuery, parts: list[str]
) -> None:
    pending = _pending_for(context, PENDING_LABEL_PICK, query)
    chosen = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
    if pending is None or chosen not in pending["ids"]:
        await query.answer(texts.BUTTON_EXPIRED)
        return
    user_data(context).pop(PENDING_LABEL_PICK, None)
    await query.answer()
    deps = get_deps(context)
    parcel = await deps.repo.get_parcel(chosen)
    if parcel is None or parcel.user_id != query.from_user.id:
        await _edit(query, texts.CARD_NOT_FOUND, None)
        return
    if pending.get("name"):
        user = await current_user(update, deps)
        await apply_label(
            update,
            context,
            user,
            parcel.tracking_number,
            pending["name"],
            pending.get("censor"),
            [pending.get("command_id"), pending.get("prompt_id")],
        )
        return
    user_data(context)[PENDING_LABEL] = {
        "code": parcel.tracking_number,
        "censor": pending.get("censor"),
        "command_id": pending.get("command_id"),
        "prompt_id": pending.get("prompt_id"),
    }
    await _edit(
        query,
        texts.LABEL_ASK.format(code=spoiler(parcel.tracking_number)),
        label_prompt_keyboard(bool(parcel.label)),
    )


async def _phone_answer(context: ContextTypes.DEFAULT_TYPE, query: CallbackQuery) -> None:
    if _pending_for(context, PENDING_PHONE, query) is None:
        await query.answer(texts.BUTTON_EXPIRED)
        return
    user_data(context).pop(PENDING_PHONE, None)
    await query.answer()
    await _edit(query, texts.CANCELLED, None)


async def _show_selection(
    context: ContextTypes.DEFAULT_TYPE, query: CallbackQuery, page: int
) -> None:
    deps = get_deps(context)
    parcels = await deps.parcels.list_for(query.from_user.id)
    page, pages, numbered = list_page_items(parcels, page)
    selected = set(user_data(context)[SELECTION]["ids"])
    header = texts.SELECT_HEADER.format(count=len(selected))
    await _edit(
        query,
        header + "\n\n" + format_parcel_list(parcels, deps.settings.tz, page=page),
        select_keyboard(numbered, page, pages, selected),
    )


async def _select_action(
    context: ContextTypes.DEFAULT_TYPE, query: CallbackQuery, parts: list[str]
) -> None:
    action = parts[0] if parts else ""
    page = (_page(parts[-1]) if len(parts) > 1 else None) or 1
    data = user_data(context)
    if action == "on":
        data[SELECTION] = {"message_id": _message_id(query), "ids": []}
        await query.answer()
        await _show_selection(context, query, page)
        return
    selection = data.get(SELECTION)
    if not isinstance(selection, dict) or selection.get("message_id") != _message_id(query):
        await query.answer(texts.BUTTON_EXPIRED)
        return
    if action == "t" and len(parts) > 2 and parts[1].isdigit():
        chosen = int(parts[1])
        ids: list[int] = selection["ids"]
        if chosen in ids:
            ids.remove(chosen)
        else:
            ids.append(chosen)
        await query.answer()
        await _show_selection(context, query, page)
    elif action == "pg":
        await query.answer()
        await _show_selection(context, query, page)
    elif action == "off":
        data.pop(SELECTION, None)
        await query.answer()
        await _show_list(context, query, page)
    elif action == "go":
        await _confirm_selection(context, query, page, selection)
    else:
        await query.answer()


async def _confirm_selection(
    context: ContextTypes.DEFAULT_TYPE, query: CallbackQuery, page: int, selection: dict
) -> None:
    listed = await get_deps(context).parcels.list_for(query.from_user.id)
    chosen = [parcel for parcel in listed if parcel.id in selection["ids"]]
    if not chosen:
        await query.answer(texts.SELECT_NONE)
        return
    data = user_data(context)
    data.pop(SELECTION, None)
    data[PENDING_REMOVE] = {
        "ids": [parcel.id for parcel in chosen],
        "command_id": None,
        "prompt_id": _message_id(query),
        "list_page": page,
    }
    await query.answer()
    await _edit(query, format_remove_confirm(chosen), remove_confirm_keyboard(len(chosen)))


async def _share_answer(
    update: Update, context: ContextTypes.DEFAULT_TYPE, query: CallbackQuery, parts: list[str]
) -> None:
    token = parts[0] if parts else ""
    choice = parts[1] if len(parts) > 1 else ""
    deps = get_deps(context)
    parcel = await shared_parcel(deps.repo, token)
    if parcel is None:
        await query.answer(texts.SHARE_NOT_FOUND)
        return
    await query.answer()
    if choice != "ok":
        await _edit(query, texts.CANCELLED, None)
        return
    user = await current_user(update, deps)
    outcome = await deps.parcels.add(user, parcel.tracking_number, None, label=parcel.label)
    text = format_add_outcome(
        outcome, deps.settings.tz, max_parcels=deps.settings.max_parcels_per_user
    )
    await _edit(query, text, card_markup(outcome))
    if outcome.kind == "needs_phone":
        user_data(context)[PENDING_PHONE] = {
            "code": outcome.code,
            "label": parcel.label,
            "prompt_id": _message_id(query),
        }
