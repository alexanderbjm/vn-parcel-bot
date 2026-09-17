import asyncio
import contextlib
import logging
import math
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from html import escape

from telegram import (
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ChatAction, ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from vn_parcel_bot import texts
from vn_parcel_bot.bot.carrier_scripts import reload_carrier_scripts
from vn_parcel_bot.bot.deps import Deps, get_deps
from vn_parcel_bot.bot.parsing import (
    parse_coordinates,
    parse_ref_and_text,
    parse_track_args,
    route_text,
)
from vn_parcel_bot.constants import RECHECK_COOLDOWN, VISION_MAX_IMAGE_BYTES
from vn_parcel_bot.db.repo import Parcel, User
from vn_parcel_bot.keyboards import (
    card_keyboard,
    check_done_keyboard,
    help_keyboard,
    history_keyboard,
    label_pick_keyboard,
    label_prompt_keyboard,
    list_keyboard,
    location_request_keyboard,
    phone_prompt_keyboard,
    remove_confirm_keyboard,
    share_open_keyboard,
    start_keyboard,
)
from vn_parcel_bot.services.formatting import (
    DEFAULT_SORT,
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
    sort_parcels,
    spoiler,
    truncate_message,
)
from vn_parcel_bot.services.geo import AreaLookupFailed
from vn_parcel_bot.services.maps import MapError
from vn_parcel_bot.services.parcels import AddOutcome
from vn_parcel_bot.services.sharing import shared_parcel
from vn_parcel_bot.services.vision import VisionResult
from vn_parcel_bot.tracking_codes import is_valid_last4

PENDING_PHONE = "pending_phone"
PENDING_LABEL = "pending_label"
PENDING_REMOVE = "pending_remove"
PENDING_LABEL_PICK = "pending_label_pick"
SELECTION = "remove_selection"
PENDING_LOCATION = "pending_location"
PENDING_KEYS = (
    PENDING_PHONE,
    PENDING_LABEL,
    PENDING_REMOVE,
    PENDING_LABEL_PICK,
    SELECTION,
    PENDING_LOCATION,
)
PHOTO_LOCKS = "photo_locks"
RECHECK_KEY = "check_cooldowns"
VISION_MEDIA_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")

MAP_COOLDOWN_SECONDS = 60
MAP_SENDS = "map_sends"
MAX_AREA_TEXT = 120

log = logging.getLogger(__name__)


async def reply(
    update: Update,
    text: str,
    reply_markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | ReplyKeyboardRemove | None = None,
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


def maps_on(deps: Deps) -> bool:
    return deps.maps is not None and deps.settings.maps_enabled


def card_markup(outcome: AddOutcome, *, maps: bool = False) -> InlineKeyboardMarkup | None:
    if outcome.kind == "needs_phone":
        return phone_prompt_keyboard()
    if outcome.parcel is None or outcome.kind not in ("added", "duplicate"):
        return None
    return card_keyboard(outcome.parcel, maps=maps)


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


async def card_view(
    deps: Deps, parcel: Parcel, user_id: int, page: int | None = None
) -> tuple[str, InlineKeyboardMarkup]:
    """The card text and buttons; with maps on, the 📍 line and the 🗺 button are added."""
    maps = deps.maps if maps_on(deps) else None
    line = None
    if maps is not None:
        user = await deps.repo.get_user(user_id)
        line = await maps.place_line(parcel, user) if user is not None else None
    text = format_parcel_card(parcel, deps.settings.tz, line)
    return text, card_keyboard(parcel, page=page, maps=maps is not None)


async def send_parcel_map(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, parcel_id: int
) -> str | None:
    """Send the parcel's map picture; returns the toast text when no picture went out."""
    deps = get_deps(context)
    maps = deps.maps if maps_on(deps) else None
    if maps is None:
        return texts.MAP_OFF
    parcel = await deps.repo.get_parcel(parcel_id)
    user = await deps.repo.get_user(user_id)
    if parcel is None or user is None or parcel.user_id != user_id:
        return texts.CARD_NOT_FOUND
    if not parcel.place:
        return texts.MAP_NO_PLACE
    # Every try counts, so a map that keeps failing is not redrawn on each tap.
    sends: dict[int, float] = context.bot_data.setdefault(MAP_SENDS, {})
    now = time.monotonic()
    for old in [key for key, sent in sends.items() if now - sent >= MAP_COOLDOWN_SECONDS]:
        del sends[old]
    if parcel_id in sends:
        return texts.MAP_TOO_SOON
    sends[parcel_id] = now
    try:
        made = await maps.photo(parcel, user)
    except MapError as exc:
        log.warning("map failed type=%s", type(exc).__name__)
        return texts.MAP_FAILED
    if made is None:
        return texts.MAP_NO_PLACE
    await deps.notifier.send_photo(chat_id, made[0], made[1])
    return None


async def _open_share(update: Update, context: ContextTypes.DEFAULT_TYPE, token: str) -> None:
    deps = get_deps(context)
    parcel = await shared_parcel(deps.repo, token)
    if parcel is None:
        await reply(update, texts.SHARE_NOT_FOUND)
        return
    user = await current_user(update, deps)
    if parcel.user_id == user.telegram_id:
        text, markup = await card_view(deps, parcel, user.telegram_id)
        await reply(update, text, reply_markup=markup)
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
        update,
        texts.WELCOME.format(name=escape(first_name or "")) + "\n\n" + format_help(),
        reply_markup=start_keyboard(),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply(update, format_help(), reply_markup=help_keyboard())


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
        reply_markup=card_markup(outcome, maps=maps_on(deps)),
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
    drop_pending(context)
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
            reply_markup=card_markup(outcome, maps=maps_on(deps)),
        )
    if needs_phone:
        await reply(update, format_needs_phone_multi(needs_phone))


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or message.text is None:
        return
    data = user_data(context)
    chat_id = _chat_id(update)
    if PENDING_LOCATION in data and message.text.strip() == texts.BTN_CANCEL_TEXT:
        data.pop(PENDING_LOCATION)
        await reply(update, texts.CANCELLED, reply_markup=ReplyKeyboardRemove())
        return
    if PENDING_LOCATION in data:
        # Telegram Desktop cannot share a location, so coordinates can be pasted instead.
        point = parse_coordinates(message.text)
        if point is not None:
            await _save_home(update, context, *point)
            await delete_messages(context, chat_id, [_message_id(message)])
            return
        if _looks_like_a_location(message.text):
            await reply(update, texts.LOCATION_TYPE_HINT)
            return
        if route_text(message.text, PENDING_PHONE in data).kind != "codes":
            await _save_written_area(update, context, message.text)
            return
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


async def list_view(
    deps: Deps, user_id: int, requested: int = 1, sort: str = DEFAULT_SORT
) -> tuple[str, int, int, list[tuple[int, Parcel]]]:
    """The list text plus the page it settled on and that page's numbered parcels.

    Each row can say where the parcel is and how far that is from the user, and the whole
    list is ordered by the mode asked for, with orders that are over kept to the end.
    """
    parcels = await deps.parcels.list_for(user_id)
    places: dict[int, str] = {}
    distances: dict[int, float] = {}
    maps = deps.maps if maps_on(deps) else None
    if maps is not None:
        user = await deps.repo.get_user(user_id)
        if user is not None:
            places, distances = await maps.list_places(parcels, user)
    ordered = sort_parcels(parcels, sort, distances)
    page, pages, numbered = list_page_items(ordered, requested)
    text = format_parcel_list(ordered, deps.settings.tz, page=page, places=places)
    return text, page, pages, numbered


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = get_deps(context)
    user = await current_user(update, deps)
    text, page, pages, numbered = await list_view(deps, user.telegram_id)
    await reply(update, text, reply_markup=list_keyboard(numbered, page, pages, recheck=True))


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
    await reply(
        update,
        format_history(parcel, events, deps.settings.tz),
        reply_markup=history_keyboard(parcel.id, maps=maps_on(deps)),
    )


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
    text, markup = await card_view(get_deps(context), parcel, parcel.user_id, card.get("page"))
    try:
        await context.bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=card["message_id"],
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
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
    """Load new carrier scripts, match carriers again and rebuild every listed parcel."""
    reloaded = await reload_carrier_scripts(deps)
    redetected = await deps.parcels.redetect_carriers(user_id)
    report = await deps.poller.run_cycle(only_user_id=user_id, wait=True, rebuild=True)
    return format_check_done(
        report.parcels_checked,
        report.new_events,
        redetected,
        rebuilt=report.rebuilt,
        reloaded=reloaded,
    )


async def check_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = get_deps(context)
    user = await current_user(update, deps)
    wait = claim_recheck(context, user.telegram_id)
    if wait is not None:
        await reply(update, texts.CHECK_TOO_SOON.format(minutes=wait))
        return
    await reply(update, texts.CHECK_STARTED)
    await reply(
        update, await recheck_all(deps, user.telegram_id), reply_markup=check_done_keyboard()
    )


async def location_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = get_deps(context)
    user = await current_user(update, deps)
    if [arg.casefold() for arg in (context.args or [])][:1] == ["off"]:
        if user.home_lat is None:
            await reply(update, texts.LOCATION_NONE)
            return
        await deps.repo.clear_home(user.telegram_id)
        log.info("home location cleared user=%s", user.telegram_id)
        await reply(update, texts.LOCATION_CLEARED)
        return
    written = " ".join(context.args or []).strip()
    if written:
        drop_pending(context)
        await _save_written_area(update, context, written)
        return
    drop_pending(context)
    user_data(context)[PENDING_LOCATION] = {"map_parcel": None}
    text = texts.LOCATION_STATUS if user.home_lat is not None else texts.LOCATION_ASK
    await reply(update, text, reply_markup=location_request_keyboard())


async def location_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """A shared location: stored rounded to ~1 km; the coordinates are never logged."""
    message = update.effective_message
    shared = getattr(message, "location", None)
    if message is None or shared is None:
        return
    await _save_home(update, context, shared.latitude, shared.longitude)


def _looks_like_a_location(text: str) -> bool:
    lowered = text.strip().casefold()
    return (
        text.strip() == texts.BTN_SEND_LOCATION
        or lowered.startswith("http")
        or "maps" in lowered
        or "goo.gl" in lowered
    )


async def _save_written_area(
    update: Update, context: ContextTypes.DEFAULT_TYPE, written: str
) -> None:
    """A written area, looked up on Photon (only the text is sent) and saved rounded to ~1 km."""
    deps = get_deps(context)
    area = " ".join(written.split())[:MAX_AREA_TEXT]
    maps = deps.maps if maps_on(deps) else None
    if maps is None:
        await reply(update, texts.LOCATION_LOOKUP_FAILED)
        return
    if not any(char.isalpha() for char in area):
        await reply(update, texts.LOCATION_AREA_NOT_FOUND.format(area=escape(area)))
        return
    try:
        found = await maps.find_area(area)
    except AreaLookupFailed:
        await reply(update, texts.LOCATION_LOOKUP_FAILED)
        return
    if found is None:
        await reply(update, texts.LOCATION_AREA_NOT_FOUND.format(area=escape(area)))
        return
    (lat, lon), name = found
    saved = texts.LOCATION_AREA_SAVED.format(area=escape(name))
    await _save_home(update, context, lat, lon, saved_text=saved)
    await delete_messages(context, _chat_id(update), [_message_id(update.effective_message)])


async def _save_home(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    lat: float,
    lon: float,
    *,
    saved_text: str = texts.LOCATION_SAVED,
) -> None:
    """Store the area rounded to ~1 km; the coordinates are never logged."""
    deps = get_deps(context)
    user = await current_user(update, deps)
    await deps.repo.set_home(user.telegram_id, lat, lon)
    log.info("home location saved user=%s", user.telegram_id)
    pending = user_data(context).pop(PENDING_LOCATION, None) or {}
    await reply(update, saved_text, reply_markup=ReplyKeyboardRemove())
    parcel_id = pending.get("map_parcel")
    if parcel_id is not None:
        chat_id = _chat_id(update) or user.telegram_id
        failure = await send_parcel_map(context, chat_id, user.telegram_id, parcel_id)
        if failure is not None:
            await reply(update, failure)


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = user_data(context)
    had_location = PENDING_LOCATION in data
    pending = [data.pop(key) for key in PENDING_KEYS if key in data]
    if not pending:
        await reply(update, texts.NOTHING_TO_CANCEL)
        return
    await reply(
        update, texts.CANCELLED, reply_markup=ReplyKeyboardRemove() if had_location else None
    )
    await delete_messages(
        context,
        _chat_id(update),
        [item.get("prompt_id") for item in pending] + [_message_id(update.effective_message)],
    )


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply(update, texts.UNKNOWN_COMMAND, reply_markup=start_keyboard())


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
    drop_pending(context)
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
            reply_markup=card_markup(outcome, maps=maps_on(deps)),
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
