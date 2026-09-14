import math
from datetime import UTC, datetime
from html import escape

from telegram import LinkPreviewOptions, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from vn_parcel_bot import texts
from vn_parcel_bot.bot.deps import Deps, get_deps
from vn_parcel_bot.bot.parsing import parse_ref_and_text, parse_track_args, route_text
from vn_parcel_bot.constants import CHECK_COOLDOWN
from vn_parcel_bot.db.repo import User
from vn_parcel_bot.services.formatting import (
    format_add_outcome,
    format_history,
    format_needs_phone_multi,
    format_parcel_list,
    parcel_title,
    truncate_message,
)
from vn_parcel_bot.tracking_codes import is_valid_last4

PENDING_PHONE = "pending_phone"


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
    await reply(update, texts.WELCOME.format(name=escape(first_name or "")) + "\n\n" + texts.HELP)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply(update, texts.HELP)


async def _add_and_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    code: str,
    last4: str | None,
) -> None:
    deps = get_deps(context)
    user = await current_user(update, deps)
    outcome = await deps.parcels.add(user, code, last4)
    if outcome.kind == "needs_phone":
        user_data(context)[PENDING_PHONE] = {"code": outcome.code}
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
        await _add_and_reply(update, context, pending["code"], route.last4)
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
