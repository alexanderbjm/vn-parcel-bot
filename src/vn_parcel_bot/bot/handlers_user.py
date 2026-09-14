import asyncio
import contextlib
import logging
import math
from datetime import UTC, datetime
from html import escape

from telegram import LinkPreviewOptions, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from vn_parcel_bot import texts
from vn_parcel_bot.bot.deps import Deps, get_deps
from vn_parcel_bot.bot.parsing import parse_ref_and_text, parse_track_args, route_text
from vn_parcel_bot.constants import CHECK_COOLDOWN, VISION_MAX_IMAGE_BYTES
from vn_parcel_bot.db.repo import User
from vn_parcel_bot.services.formatting import (
    format_add_outcome,
    format_help,
    format_history,
    format_links,
    format_needs_phone_multi,
    format_parcel_list,
    parcel_title,
    truncate_message,
)
from vn_parcel_bot.services.vision import VisionResult
from vn_parcel_bot.tracking_codes import is_valid_last4

PENDING_PHONE = "pending_phone"
PHOTO_LOCKS = "photo_locks"
VISION_MEDIA_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")

log = logging.getLogger(__name__)


async def reply(update: Update, text: str) -> None:
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(
        truncate_message(text),
        parse_mode=ParseMode.HTML,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    if outcome.kind == "needs_phone":
        user_data(context)[PENDING_PHONE] = {"code": outcome.code, "label": label}
    else:
        user_data(context).pop(PENDING_PHONE, None)
    await reply(
        update,
        format_add_outcome(
            outcome, deps.settings.tz, max_parcels=deps.settings.max_parcels_per_user
        ),
    )


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
        )
    if needs_phone:
        await reply(update, format_needs_phone_multi(needs_phone))


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or message.text is None:
        return
    data = user_data(context)
    route = route_text(message.text, PENDING_PHONE in data)
    if route.kind == "phone_for_pending":
        pending = data.pop(PENDING_PHONE)
        await _add_and_reply(update, context, pending["code"], route.last4, pending.get("label"))
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
    await reply(update, format_parcel_list(parcels, deps.settings.tz))


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await reply(update, texts.USAGE_REF.format(command="status"))
        return
    deps = get_deps(context)
    user = await current_user(update, deps)
    ref = " ".join(context.args)
    found = await deps.parcels.history(user.telegram_id, ref)
    if found is None:
        await reply(update, texts.PARCEL_NOT_FOUND.format(ref=escape(ref)))
        return
    parcel, events = found
    await reply(update, format_history(parcel, events, deps.settings.tz))


async def label_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    parsed = parse_ref_and_text(context.args or [])
    if parsed is None:
        await reply(update, texts.USAGE_LABEL)
        return
    ref, label = parsed
    deps = get_deps(context)
    user = await current_user(update, deps)
    parcel = await deps.parcels.rename(user.telegram_id, ref, label)
    if parcel is None:
        await reply(update, texts.PARCEL_NOT_FOUND.format(ref=escape(ref)))
    elif parcel.label:
        await reply(update, texts.LABEL_SET.format(label=escape(parcel.label)))
    else:
        await reply(update, texts.LABEL_CLEARED.format(code=escape(parcel.tracking_number)))


async def remove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await reply(update, texts.USAGE_REF.format(command="remove"))
        return
    deps = get_deps(context)
    user = await current_user(update, deps)
    ref = " ".join(context.args)
    parcel = await deps.parcels.remove(user.telegram_id, ref)
    if parcel is None:
        await reply(update, texts.PARCEL_NOT_FOUND.format(ref=escape(ref)))
    else:
        await reply(update, texts.REMOVED.format(title=parcel_title(parcel)))


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


async def check_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = get_deps(context)
    user = await current_user(update, deps)
    cooldowns: dict[int, datetime] = context.bot_data.setdefault("check_cooldowns", {})
    now = datetime.now(UTC)
    last = cooldowns.get(user.telegram_id)
    if last is not None and now - last < CHECK_COOLDOWN:
        remaining = (CHECK_COOLDOWN - (now - last)).total_seconds()
        await reply(update, texts.CHECK_TOO_SOON.format(minutes=math.ceil(remaining / 60)))
        return
    cooldowns[user.telegram_id] = now
    await reply(update, texts.CHECK_STARTED)
    report = await deps.poller.run_cycle(only_user_id=user.telegram_id, wait=True)
    await reply(
        update,
        texts.CHECK_DONE.format(checked=report.parcels_checked, new_events=report.new_events),
    )


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if user_data(context).pop(PENDING_PHONE, None) is None:
        await reply(update, texts.NOTHING_TO_CANCEL)
    else:
        await reply(update, texts.CANCELLED)


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
                code=escape(code), carrier_suffix=escape(carrier_suffix)
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
        if single:
            if outcome.kind == "needs_phone":
                user_data(context)[PENDING_PHONE] = {"code": outcome.code, "label": label}
            else:
                user_data(context).pop(PENDING_PHONE, None)
        body = format_add_outcome(
            outcome, deps.settings.tz, max_parcels=deps.settings.max_parcels_per_user
        )
        await reply(update, f"{_vision_header(result, code, phone_last4)}\n\n{body}")
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
            order_id=escape(order_id), links=format_links(order_id, ())
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
