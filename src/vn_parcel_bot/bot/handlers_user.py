import asyncio
import contextlib
import logging
import math
from collections.abc import Iterable
from datetime import UTC, datetime
from html import escape

from telegram import InlineKeyboardMarkup, LinkPreviewOptions, Message, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from vn_parcel_bot import texts
from vn_parcel_bot.bot.deps import Deps, get_deps
from vn_parcel_bot.bot.parsing import parse_ref_and_text, parse_track_args, route_text
from vn_parcel_bot.constants import RECHECK_COOLDOWN, VISION_MAX_IMAGE_BYTES
from vn_parcel_bot.db.repo import Parcel, User
from vn_parcel_bot.keyboards import (
    card_keyboard,
    label_pick_keyboard,
    label_prompt_keyboard,
    list_keyboard,
    phone_prompt_keyboard,
    remove_confirm_keyboard,
    share_open_keyboard,
)
from vn_parcel_bot.services.formatting import (
    format_add_outcome,
    format_check_done,
    format_help,
    format_history,
    format_links,
    format_needs_phone_multi,
    format_parcel_card,
    format_parcel_list,
    format_remove_confirm,
    list_page_items,
    parcel_carrier_label,
    parcel_title,
    ref_text,
    spoiler,
    truncate_message,
)
from vn_parcel_bot.services.parcels import AddOutcome
from vn_parcel_bot.services.sharing import shared_parcel
from vn_parcel_bot.services.vision import VisionResult
from vn_parcel_bot.tracking_codes import is_valid_last4

PENDING_PHONE = "pending_phone"
PENDING_LABEL = "pending_label"
PENDING_REMOVE = "pending_remove"
PENDING_LABEL_PICK = "pending_label_pick"
SELECTION = "remove_selection"
PENDING_KEYS = (PENDING_PHONE, PENDING_LABEL, PENDING_REMOVE, PENDING_LABEL_PICK, SELECTION)
PHOTO_LOCKS = "photo_locks"
RECHECK_KEY = "check_cooldowns"
VISION_MEDIA_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")

log = logging.getLogger(__name__)


async def reply(
    update: Update, text: str, reply_markup: InlineKeyboardMarkup | None = None
) -> Message | None:
    message = update.effective_message
    if message is None:
        return None
    return await message.reply_text(
        truncate_message(text),
        parse_mode=ParseMode.HTML,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
        reply_markup=reply_markup,
    )


def card_markup(outcome: AddOutcome) -> InlineKeyboardMarkup | None:
    if outcome.kind == "needs_phone":
        return phone_prompt_keyboard()
    if outcome.parcel is None or outcome.kind not in ("added", "duplicate"):
        return None
    return card_keyboard(outcome.parcel)


async def current_user(update: Update, deps: Deps) -> User:
    tg_user = update.effective_user
    assert tg_user is not None
    user = await deps.repo.get_user(tg_user.id)
    if user is None:
        user = await deps.repo.upsert_user(
            tg_user.id, now=datetime.now(UTC), name=tg_user.full_name
        )
    return user


def user_data(context: ContextTypes.DEFAULT_TYPE) -> dict:
    data = context.user_data
    assert data is not None
    return data


def _chat_id(update: Update) -> int | None:
    return getattr(update.effective_chat, "id", None)


def _message_id(message: object) -> int | None:
    return getattr(message, "message_id", None)


def drop_pending(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = user_data(context)
    for key in PENDING_KEYS:
        data.pop(key, None)


async def delete_messages(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int | None, message_ids: Iterable[int | None]
) -> None:
    if chat_id is None:
        return
    for message_id in message_ids:
        if message_id is None:
            continue
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except TelegramError as exc:
            log.info("message delete failed type=%s", type(exc).__name__)


async def _open_share(update: Update, context: ContextTypes.DEFAULT_TYPE, token: str) -> None:
    deps = get_deps(context)
    parcel = await shared_parcel(deps.repo, token)
    if parcel is None:
        await reply(update, texts.SHARE_NOT_FOUND)
        return
    user = await current_user(update, deps)
    if parcel.user_id == user.telegram_id:
        await reply(
            update,
            format_parcel_card(parcel, deps.settings.tz),
            reply_markup=card_keyboard(parcel),
        )
        return
    await reply(
        update,
        texts.SHARE_OPEN.format(title=parcel_title(parcel), carrier=parcel_carrier_label(parcel)),
        reply_markup=share_open_keyboard(token),
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    if args and args[0].startswith("s_"):
        await _open_share(update, context, args[0][2:])
        return
    first_name = update.effective_user.first_name if update.effective_user else ""
    await reply(
        update, texts.WELCOME.format(name=escape(first_name or "")) + "\n\n" + format_help()
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply(update, format_help())


async def _add_and_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    code: str,
    last4: str | None,
    label: str | None = None,
) -> None:
    deps = get_deps(context)
    user = await current_user(update, deps)
    outcome = await deps.parcels.add(user, code, last4, label=label)
    drop_pending(context)
    sent = await reply(
        update,
        format_add_outcome(
            outcome, deps.settings.tz, max_parcels=deps.settings.max_parcels_per_user
        ),
        reply_markup=card_markup(outcome),
    )
    if outcome.kind == "needs_phone":
        user_data(context)[PENDING_PHONE] = {
            "code": outcome.code,
            "label": label,
            "prompt_id": _message_id(sent),
        }


async def track_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    parsed = parse_track_args(context.args or [])
    if parsed is None:
        await reply(update, texts.USAGE_TRACK)
        return
    code, last4 = parsed
    await _add_and_reply(update, context, code, last4)


async def _add_many(
    update: Update, context: ContextTypes.DEFAULT_TYPE, codes: tuple[str, ...]
) -> None:
    deps = get_deps(context)
    user = await current_user(update, deps)
    needs_phone: list[str] = []
    for code in codes:
        outcome = await deps.parcels.add(user, code)
        if outcome.kind == "needs_phone":
            needs_phone.append(outcome.code or code)
            continue
        await reply(
            update,
            format_add_outcome(
                outcome, deps.settings.tz, max_parcels=deps.settings.max_parcels_per_user
            ),
            reply_markup=card_markup(outcome),
        )
    if needs_phone:
        await reply(update, format_needs_phone_multi(needs_phone))


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or message.text is None:
        return
    data = user_data(context)
    chat_id = _chat_id(update)
    if PENDING_LABEL in data:
        pending = data.pop(PENDING_LABEL)
        user = await current_user(update, get_deps(context))
        await apply_label(
            update,
            context,
            user,
            pending["code"],
            message.text,
            pending.get("censor"),
            [pending.get("command_id"), pending.get("prompt_id"), _message_id(message)],
            card=pending.get("card"),
        )
        return
    route = route_text(message.text, PENDING_PHONE in data)
    if route.kind == "phone_for_pending":
        pending = data.pop(PENDING_PHONE)
        await _add_and_reply(update, context, pending["code"], route.last4, pending.get("label"))
        await delete_messages(context, chat_id, [pending.get("prompt_id"), _message_id(message)])
    elif route.kind == "codes":
        data.pop(PENDING_PHONE, None)
        if len(route.codes) == 1:
            await _add_and_reply(update, context, route.codes[0], None)
        else:
            await _add_many(update, context, route.codes)
    elif route.kind == "invalid_phone":
        await reply(update, texts.INVALID_PHONE)
    else:
        await reply(update, texts.UNKNOWN_CODE)


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = get_deps(context)
    user = await current_user(update, deps)
    parcels = await deps.parcels.list_for(user.telegram_id)
    page, pages, numbered = list_page_items(parcels, 1)
    await reply(
        update,
        format_parcel_list(parcels, deps.settings.tz, page=page),
        reply_markup=list_keyboard(numbered, page, pages, recheck=True),
    )


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await reply(update, texts.USAGE_REF.format(command="status"))
        return
    deps = get_deps(context)
    user = await current_user(update, deps)
    ref = " ".join(context.args)
    found = await deps.parcels.history(user.telegram_id, ref)
    if found is None:
        await reply(update, texts.PARCEL_NOT_FOUND.format(ref=ref_text(ref)))
        return
    parcel, events = found
    await reply(update, format_history(parcel, events, deps.settings.tz))


def _censor_target(context: ContextTypes.DEFAULT_TYPE, replied: Message) -> dict | None:
    sender = getattr(replied, "from_user", None)
    if sender is None or sender.id != context.bot.id or not getattr(replied, "text", None):
        return None
    return {"message_id": replied.message_id, "text_html": replied.text_html}


async def _censor(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int | None,
    target: dict | None,
    tracking_number: str,
) -> None:
    if chat_id is None or not target or tracking_number not in target["text_html"]:
        return
    # Blur the code where the replied message still shows it in clear; keep it visible.
    blurred = spoiler(tracking_number)
    original = target["text_html"]
    text = original.replace(blurred, tracking_number).replace(tracking_number, blurred)
    if text == original:
        return
    try:
        await context.bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=target["message_id"],
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    except TelegramError as exc:
        log.info("message censor failed type=%s", type(exc).__name__)


async def _refresh_card(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int | None, card: dict | None, parcel: Parcel
) -> None:
    if chat_id is None or not card:
        return
    try:
        await context.bot.edit_message_text(
            format_parcel_card(parcel, get_deps(context).settings.tz),
            chat_id=chat_id,
            message_id=card["message_id"],
            parse_mode=ParseMode.HTML,
            reply_markup=card_keyboard(parcel, page=card.get("page")),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    except TelegramError as exc:
        log.info("card refresh failed type=%s", type(exc).__name__)


async def apply_label(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
    code: str,
    label: str | None,
    target: dict | None,
    delete_ids: Iterable[int | None],
    card: dict | None = None,
) -> None:
    deps = get_deps(context)
    parcel = await deps.parcels.rename(user.telegram_id, code, label)
    if parcel is None:
        await reply(update, texts.PARCEL_NOT_FOUND.format(ref=spoiler(code)))
        return
    chat_id = _chat_id(update)
    await _censor(context, chat_id, target, parcel.tracking_number)
    await _refresh_card(context, chat_id, card, parcel)
    code = spoiler(parcel.tracking_number)
    if parcel.label:
        await reply(update, texts.LABEL_SET.format(label=escape(parcel.label), code=code))
    else:
        await reply(update, texts.LABEL_CLEARED.format(code=code))
    await delete_messages(context, chat_id, delete_ids)


async def label_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    deps = get_deps(context)
    user = await current_user(update, deps)
    args = [arg for arg in (context.args or []) if arg.strip()]
    replied = getattr(message, "reply_to_message", None)
    replied_text = None if replied is None else (replied.text or replied.caption)
    if replied is not None and replied_text:
        matches = await deps.parcels.find_in_text(user.telegram_id, replied_text)
        if not matches:
            await reply(update, texts.LABEL_REPLY_NOT_FOUND)
            return
        if len(matches) > 1:
            drop_pending(context)
            picker = await reply(
                update, texts.LABEL_PICK, reply_markup=label_pick_keyboard(matches)
            )
            user_data(context)[PENDING_LABEL_PICK] = {
                "ids": [match.id for match in matches],
                "name": " ".join(args) or None,
                "censor": _censor_target(context, replied),
                "command_id": _message_id(message),
                "prompt_id": _message_id(picker),
            }
            return
        parcel = matches[0]
        name = " ".join(args) or None
        target = _censor_target(context, replied)
    else:
        parsed = parse_ref_and_text(args)
        if parsed is None:
            await reply(update, texts.USAGE_LABEL)
            return
        ref, name = parsed
        found = await deps.parcels.resolve(user.telegram_id, ref)
        if found is None:
            await reply(update, texts.PARCEL_NOT_FOUND.format(ref=ref_text(ref)))
            return
        parcel = found
        target = None
    if name is None:
        drop_pending(context)
        prompt = await reply(
            update,
            texts.LABEL_ASK.format(code=spoiler(parcel.tracking_number)),
            reply_markup=label_prompt_keyboard(bool(parcel.label)),
        )
        user_data(context)[PENDING_LABEL] = {
            "code": parcel.tracking_number,
            "censor": target,
            "command_id": _message_id(message),
            "prompt_id": _message_id(prompt),
        }
        return
    await apply_label(
        update, context, user, parcel.tracking_number, name, target, [_message_id(message)]
    )


async def remove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await reply(update, texts.USAGE_REF.format(command="remove"))
        return
    deps = get_deps(context)
    user = await current_user(update, deps)
    parcels, missing = await deps.parcels.resolve_many(user.telegram_id, context.args)
    if not parcels:
        refs = ", ".join(ref_text(ref) for ref in missing)
        await reply(update, texts.PARCEL_NOT_FOUND.format(ref=refs))
        return
    drop_pending(context)
    prompt = await reply(
        update,
        format_remove_confirm(parcels, missing),
        reply_markup=remove_confirm_keyboard(len(parcels)),
    )
    user_data(context)[PENDING_REMOVE] = {
        "ids": [parcel.id for parcel in parcels],
        "command_id": _message_id(update.effective_message),
        "prompt_id": _message_id(prompt),
    }


async def phone_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = get_deps(context)
    user = await current_user(update, deps)
    args = context.args or []
    if not args:
        if user.default_phone_last4:
            await reply(update, texts.PHONE_SHOW.format(last4=user.default_phone_last4))
        else:
            await reply(update, texts.PHONE_NONE)
    elif args[0].casefold() == "clear":
        await deps.parcels.set_default_phone(user.telegram_id, None)
        await reply(update, texts.PHONE_CLEARED)
    elif is_valid_last4(args[0]):
        await deps.parcels.set_default_phone(user.telegram_id, args[0])
        await reply(update, texts.PHONE_SET.format(last4=args[0]))
    else:
        await reply(update, texts.INVALID_PHONE)


def claim_recheck(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> int | None:
    """Start a check-all for this user, or return the minutes left on the cooldown."""
    cooldowns: dict[int, datetime] = context.bot_data.setdefault(RECHECK_KEY, {})
    now = datetime.now(UTC)
    last = cooldowns.get(user_id)
    if last is not None and now - last < RECHECK_COOLDOWN:
        return math.ceil((RECHECK_COOLDOWN - (now - last)).total_seconds() / 60)
    cooldowns[user_id] = now
    return None


async def recheck_all(deps: Deps, user_id: int) -> str:
    """Match every active parcel's carrier again, check them all now and summarise."""
    redetected = await deps.parcels.redetect_carriers(user_id)
    report = await deps.poller.run_cycle(only_user_id=user_id, wait=True)
    return format_check_done(report.parcels_checked, report.new_events, redetected)


async def check_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = get_deps(context)
    user = await current_user(update, deps)
    wait = claim_recheck(context, user.telegram_id)
    if wait is not None:
        await reply(update, texts.CHECK_TOO_SOON.format(minutes=wait))
        return
    await reply(update, texts.CHECK_STARTED)
    await reply(update, await recheck_all(deps, user.telegram_id))


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = user_data(context)
    pending = [data.pop(key) for key in PENDING_KEYS if key in data]
    if not pending:
        await reply(update, texts.NOTHING_TO_CANCEL)
        return
    await reply(update, texts.CANCELLED)
    await delete_messages(
        context,
        _chat_id(update),
        [item.get("prompt_id") for item in pending] + [_message_id(update.effective_message)],
    )


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply(update, texts.UNKNOWN_COMMAND)


def _photo_lock(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> asyncio.Lock:
    locks: dict[int, asyncio.Lock] = context.bot_data.setdefault(PHOTO_LOCKS, {})
    return locks.setdefault(user_id, asyncio.Lock())


def _caption_last4(caption: str | None) -> str | None:
    for word in (caption or "").split():
        cleaned = word.strip(" ,;.:()[]")
        if is_valid_last4(cleaned):
            return cleaned
    return None


def _vision_header(result: VisionResult, code: str | None, phone_last4: str | None) -> str:
    parts = [texts.VISION_DETECTED_HEADER]
    if result.product_name:
        parts.append(texts.VISION_PRODUCT.format(name=escape(result.product_name)))
    if code is not None:
        carrier_suffix = f" ({result.carrier})" if result.carrier else ""
        parts.append(
            texts.VISION_DETECTED_ITEM.format(
                code=spoiler(code), carrier_suffix=escape(carrier_suffix)
            )
        )
    if phone_last4:
        parts.append(texts.VISION_DETECTED_PHONE.format(phone=escape(phone_last4)))
    return "\n".join(parts)


async def _add_codes_from_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    result: VisionResult,
    phone_last4: str | None,
) -> None:
    deps = get_deps(context)
    user = await current_user(update, deps)
    label = result.product_name
    single = len(result.tracking_codes) == 1
    needs_phone: list[str] = []
    for code in result.tracking_codes:
        outcome = await deps.parcels.add(user, code, phone_last4, label=label)
        if outcome.kind == "needs_phone" and not single:
            needs_phone.append(outcome.code or code)
            continue
        body = format_add_outcome(
            outcome, deps.settings.tz, max_parcels=deps.settings.max_parcels_per_user
        )
        sent = await reply(
            update,
            f"{_vision_header(result, code, phone_last4)}\n\n{body}",
            reply_markup=card_markup(outcome),
        )
        if single:
            if outcome.kind == "needs_phone":
                user_data(context)[PENDING_PHONE] = {
                    "code": outcome.code,
                    "label": label,
                    "prompt_id": _message_id(sent),
                }
            else:
                user_data(context).pop(PENDING_PHONE, None)
    if needs_phone:
        await reply(update, format_needs_phone_multi(needs_phone))


async def _reply_to_vision_result(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    caption: str | None,
    result: VisionResult,
) -> None:
    if result.error == "not_configured":
        await reply(update, texts.VISION_NOT_CONFIGURED)
        return
    if result.error:
        await reply(update, texts.VISION_ERROR)
        return
    log.info(
        "photo read codes=%d order_ids=%d product=%s",
        len(result.tracking_codes),
        len(result.order_ids),
        "yes" if result.product_name else "no",
    )
    phone_last4 = result.phone_last4 or _caption_last4(caption)
    if result.tracking_codes:
        await _add_codes_from_photo(update, context, result, phone_last4)
        return
    if result.order_ids:
        order_id = result.order_ids[0]
        body = texts.VISION_ORDER_ONLY.format(
            order_id=spoiler(order_id), links=format_links(order_id, ())
        )
        await reply(update, f"{_vision_header(result, None, None)}\n\n{body}")
        return
    await reply(update, texts.VISION_NO_DATA)


async def photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or update.effective_user is None:
        return
    deps = get_deps(context)
    if deps.vision is None or not deps.vision.is_configured:
        await reply(update, texts.VISION_NOT_CONFIGURED)
        return

    if message.photo:
        file_id, media_type = message.photo[-1].file_id, "image/jpeg"
    elif message.document is not None:
        document = message.document
        if (
            document.mime_type not in VISION_MEDIA_TYPES
            or (document.file_size or 0) > VISION_MAX_IMAGE_BYTES
        ):
            await reply(update, texts.VISION_UNSUPPORTED_IMAGE)
            return
        file_id, media_type = document.file_id, document.mime_type
    else:
        return

    async with _photo_lock(context, update.effective_user.id):
        if update.effective_chat is not None:
            with contextlib.suppress(Exception):
                await update.effective_chat.send_action(action=ChatAction.TYPING)
        try:
            telegram_file = await context.bot.get_file(file_id)
            image_bytes = bytes(await telegram_file.download_as_bytearray())
        except TelegramError as exc:
            log.warning("photo download failed type=%s", type(exc).__name__)
            await reply(update, texts.VISION_ERROR)
            return
        result = await deps.vision.analyze_image(image_bytes, media_type)
        await _reply_to_vision_result(update, context, message.caption, result)
