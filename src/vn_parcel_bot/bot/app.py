import logging
from datetime import UTC, datetime
from html import escape

from telegram import Update
from telegram.error import Conflict, NetworkError, TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)
from telegram.request import HTTPXRequest

from vn_parcel_bot import texts
from vn_parcel_bot.bot.auth import gate
from vn_parcel_bot.bot.commands import BOT_COMMANDS
from vn_parcel_bot.bot.deps import Deps, get_deps
from vn_parcel_bot.bot.handlers_admin import allow_cmd, health_cmd, revoke_cmd, users_cmd
from vn_parcel_bot.bot.handlers_user import (
    cancel_cmd,
    check_cmd,
    help_cmd,
    label_cmd,
    list_cmd,
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
from vn_parcel_bot.carriers import CARRIERS
from vn_parcel_bot.carriers.http import make_http_client
from vn_parcel_bot.config import Settings
from vn_parcel_bot.constants import ERROR_ALERT_COOLDOWN, FIRST_POLL_DELAY_SECONDS
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.parcels import ParcelService
from vn_parcel_bot.services.poller import Poller
from vn_parcel_bot.services.vision import VisionService

log = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def build_application(settings: Settings) -> Application:
    builder = (
        Application.builder()
        .token(settings.telegram_bot_token)
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
        ("check", check_cmd),
        ("cancel", cancel_cmd),
        ("allow", allow_cmd),
        ("revoke", revoke_cmd),
        ("users", users_cmd),
        ("health", health_cmd),
    ]:
        app.add_handler(CommandHandler(name, callback, filters=private))
    app.add_handler(MessageHandler(filters.PHOTO & private, photo_message))
    app.add_handler(MessageHandler(filters.Document.IMAGE & private, photo_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & private, text_message))
    app.add_handler(MessageHandler(filters.COMMAND & private, unknown_command))
    app.add_error_handler(on_error)
    return app


async def _post_init(app: Application) -> None:
    settings: Settings = app.bot_data["settings"]
    repo = await Repository.open(settings.db_path)
    await repo.upsert_user(
        settings.admin_telegram_id, now=_utc_now(), is_allowed=True, is_admin=True
    )
    http = make_http_client(settings)
    notifier = TelegramNotifier(app.bot)
    parcels = ParcelService(repo, CARRIERS, http, settings, _utc_now)
    poller = Poller(repo, CARRIERS, http, notifier, settings, _utc_now)
    vision = VisionService(settings, http)
    app.bot_data["deps"] = Deps(settings, repo, http, parcels, poller, notifier, vision=vision)
    assert app.job_queue is not None, "install python-telegram-bot[job-queue]"
    app.job_queue.run_repeating(
        poll_job, interval=settings.poll_interval, first=FIRST_POLL_DELAY_SECONDS, name="poll"
    )
    await app.bot.set_my_commands(BOT_COMMANDS)
    log.info("bot started as @%s", app.bot.username)


async def _post_shutdown(app: Application) -> None:
    deps: Deps | None = app.bot_data.get("deps")
    if deps is not None:
        await deps.http.aclose()
        await deps.repo.close()
    log.info("bot stopped")


async def poll_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await get_deps(context).poller.run_cycle()


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
