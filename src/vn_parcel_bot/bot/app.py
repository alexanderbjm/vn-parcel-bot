import asyncio
import logging
from datetime import UTC, datetime
from html import escape

from telegram import BotCommandScopeChat, Update
from telegram.constants import ParseMode
from telegram.error import Conflict, NetworkError, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    Defaults,
    JobQueue,
    MessageHandler,
    TypeHandler,
    filters,
)
from telegram.request import HTTPXRequest

from vn_parcel_bot import texts
from vn_parcel_bot.bot.auth import gate
from vn_parcel_bot.bot.carrier_scripts import alert_rejections
from vn_parcel_bot.bot.commands import ADMIN_COMMANDS, BOT_COMMANDS
from vn_parcel_bot.bot.deps import Deps, get_deps
from vn_parcel_bot.bot.handlers_admin import (
    allow_cmd,
    health_cmd,
    hozk_cmd,
    revoke_cmd,
    sticker_cmd,
    users_cmd,
)
from vn_parcel_bot.bot.handlers_callback import callback_query
from vn_parcel_bot.bot.handlers_user import (
    cancel_cmd,
    check_cmd,
    help_cmd,
    label_cmd,
    list_cmd,
    location_cmd,
    location_message,
    phone_cmd,
    photo_message,
    remove_cmd,
    start,
    status_cmd,
    text_message,
    track_cmd,
    unknown_command,
)
from vn_parcel_bot.bot.notifier import TelegramNotifier
from vn_parcel_bot.build_info import (
    deployed_revision_async,
    deployed_revision_sha_async,
    revision_commits_async,
)
from vn_parcel_bot.carriers.http import make_http_client
from vn_parcel_bot.carriers.registry import CarrierRegistry, set_registry
from vn_parcel_bot.config import Settings
from vn_parcel_bot.constants import (
    ERROR_ALERT_COOLDOWN,
    FIRST_POLL_DELAY_SECONDS,
    MODULE_REFRESH_SECONDS,
    POLL_TICK_SECONDS,
)
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.digest import DigestService
from vn_parcel_bot.services.formatting import format_update_notice
from vn_parcel_bot.services.geo import Geocoder
from vn_parcel_bot.services.maps import TileCache
from vn_parcel_bot.services.parcel_maps import ParcelMaps
from vn_parcel_bot.services.parcels import ParcelService
from vn_parcel_bot.services.poller import Poller, build_seventeen
from vn_parcel_bot.services.stickers import covers_dir, register_icons, sweep_covers
from vn_parcel_bot.services.vision_engines import build_vision_engine

log = logging.getLogger(__name__)

UPDATE_META_KEY = "notify:revision"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def build_application(settings: Settings) -> Application:
    builder = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .defaults(Defaults(parse_mode=ParseMode.HTML))
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
    )
    if settings.telegram_proxy_url:
        builder = builder.request(
            HTTPXRequest(proxy=settings.telegram_proxy_url)
        ).get_updates_request(HTTPXRequest(proxy=settings.telegram_proxy_url))
    app = builder.build()
    app.bot_data["settings"] = settings
    app.add_handler(TypeHandler(Update, gate), group=-1)
    private = filters.ChatType.PRIVATE
    for name, callback in [
        ("start", start),
        ("help", help_cmd),
        ("track", track_cmd),
        ("list", list_cmd),
        ("status", status_cmd),
        ("label", label_cmd),
        ("remove", remove_cmd),
        ("phone", phone_cmd),
        ("location", location_cmd),
        ("check", check_cmd),
        ("cancel", cancel_cmd),
        ("allow", allow_cmd),
        ("revoke", revoke_cmd),
        ("users", users_cmd),
        ("health", health_cmd),
        ("sticker", sticker_cmd),
        ("hozk", hozk_cmd),
    ]:
        app.add_handler(CommandHandler(name, callback, filters=private))
    app.add_handler(MessageHandler(filters.PHOTO & private, photo_message))
    app.add_handler(MessageHandler(filters.Document.IMAGE & private, photo_message))
    app.add_handler(MessageHandler(filters.LOCATION & private, location_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & private, text_message))
    app.add_handler(MessageHandler(filters.COMMAND & private, unknown_command))
    app.add_handler(CallbackQueryHandler(callback_query))
    app.add_error_handler(on_error)
    return app


async def announce_update(deps: Deps) -> None:
    """DM the admin once per deployed revision, with what changed in it.

    The bot restarts at every logon as well as after every deploy, so the notice is keyed on the
    commit rather than on the start: the admin hears about it when the running code changes, not
    on every reboot. The body lists the commits since the revision it last reported.
    """
    revision = await deployed_revision_async()
    sha = await deployed_revision_sha_async()
    if revision is None or sha is None:
        return
    recorded = await deps.repo.get_meta(UPDATE_META_KEY)
    # Earlier releases stored "sha · date"; only the sha is needed to bound the commit range.
    previous = recorded.split()[0] if recorded else None
    if previous == sha:
        return
    # With no recorded sha (the first notice after this shipped) there is no range to bound, so
    # the log falls back to the most recent commits rather than sending a brief with no content.
    subjects = await revision_commits_async(previous)
    try:
        await deps.notifier.send(
            deps.settings.admin_telegram_id,
            format_update_notice(revision, subjects),
            silent=False,
        )
    except Exception:
        # Leave the meta key unwritten so the next start tries again.
        log.warning("update notice failed revision=%s", revision, exc_info=True)
        return
    await deps.repo.set_meta(UPDATE_META_KEY, sha)


async def _post_init(app: Application) -> None:
    settings: Settings = app.bot_data["settings"]
    repo = await Repository.open(settings.db_path)
    await repo.upsert_user(
        settings.admin_telegram_id, now=_utc_now(), is_allowed=True, is_admin=True
    )
    http = make_http_client(settings)
    notifier = TelegramNotifier(app.bot)
    registry = CarrierRegistry.load()
    set_registry(registry)
    parcels = ParcelService(repo, registry, http, settings, _utc_now)
    tile_cache = TileCache(http, settings.db_path.parent / "tiles")
    maps = ParcelMaps(repo, Geocoder(repo, http, _utc_now), tile_cache.get, settings)
    poller = Poller(
        repo,
        registry,
        http,
        notifier,
        settings,
        _utc_now,
        maps=maps,
        seventeen=build_seventeen(settings),
    )
    vision = build_vision_engine(settings, http)
    digests = DigestService(repo, notifier, settings, _utc_now)
    app.bot_data["deps"] = Deps(
        settings,
        repo,
        http,
        parcels,
        poller,
        notifier,
        vision=vision,
        digests=digests,
        registry=registry,
        maps=maps,
    )
    await announce_update(app.bot_data["deps"])
    await alert_rejections(app.bot_data["deps"], registry.startup_rejections)
    await register_icons(repo, notifier, settings.admin_telegram_id)
    await sweep_covers(repo, covers_dir(settings.db_path))
    assert app.job_queue is not None, "install python-telegram-bot[job-queue]"
    schedule_jobs(app.job_queue, settings)
    await app.bot.set_my_commands(BOT_COMMANDS)
    try:
        await app.bot.set_my_commands(
            BOT_COMMANDS + ADMIN_COMMANDS, scope=BotCommandScopeChat(settings.admin_telegram_id)
        )
    except TelegramError as exc:
        log.info("admin command menu not set type=%s", type(exc).__name__)
    log.info("bot started as @%s", app.bot.username)


async def _post_shutdown(app: Application) -> None:
    deps: Deps | None = app.bot_data.get("deps")
    if deps is not None:
        await deps.http.aclose()
        await deps.repo.close()
    log.info("bot stopped")


async def carrier_modules_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = get_deps(context)
    if deps.registry is None:
        return
    report = await asyncio.to_thread(deps.registry.refresh)
    await alert_rejections(deps, report.rejected)


async def poll_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await get_deps(context).poller.run_cycle()


async def digest_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    digests = get_deps(context).digests
    if digests is not None:
        await digests.send_all()


def schedule_jobs(job_queue: JobQueue, settings: Settings) -> None:
    job_queue.run_repeating(
        poll_job, interval=POLL_TICK_SECONDS, first=FIRST_POLL_DELAY_SECONDS, name="poll"
    )
    job_queue.run_repeating(
        carrier_modules_job,
        interval=MODULE_REFRESH_SECONDS,
        first=MODULE_REFRESH_SECONDS,
        name="carrier modules",
    )
    for slot in settings.digest_times:
        job_queue.run_daily(
            digest_job,
            time=slot.replace(tzinfo=settings.tz),
            name=f"digest {slot.strftime('%H:%M')}",
        )
    if settings.digest_times:
        log.info(
            "digests scheduled at %s",
            ", ".join(slot.strftime("%H:%M") for slot in settings.digest_times),
        )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    if isinstance(error, Conflict):
        log.critical("another bot instance is polling with this token")
        context.bot_data["exit_code"] = 1
        context.application.stop_running()
        return
    if isinstance(error, NetworkError):
        log.warning("telegram network error: %s", type(error).__name__)
        return
    log.error("unhandled error", exc_info=error)
    if isinstance(update, Update) and update.effective_message is not None:
        try:
            await update.effective_message.reply_text(texts.ERROR_GENERIC)
        except TelegramError:
            log.warning("could not send the generic error reply")
    deps: Deps | None = context.bot_data.get("deps")
    if deps is None:
        return
    now = _utc_now()
    last = await deps.repo.get_meta("alert:error")
    if last is not None and now - datetime.fromisoformat(last) < ERROR_ALERT_COOLDOWN:
        return
    await deps.repo.set_meta("alert:error", now.isoformat())
    await deps.notifier.send(
        deps.settings.admin_telegram_id,
        texts.ALERT_ERROR.format(detail=escape(type(error).__name__)),
    )
