import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update

from vn_parcel_bot.bot.app import build_application
from vn_parcel_bot.config import ConfigError, Settings
from vn_parcel_bot.logging_setup import setup_logging
from vn_parcel_bot.single_instance import SingleInstanceError, SingleInstanceLock


def _write_startup_error(log_dir: Path, message: str) -> None:
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "startup-error.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now(UTC).isoformat(timespec='seconds')} {message}\n")
    except OSError:
        pass


def main() -> int:
    load_dotenv(Path.cwd() / ".env")
    try:
        settings = Settings.from_env(os.environ)
    except ConfigError as exc:
        _write_startup_error(Path(os.environ.get("LOG_DIR") or "logs"), str(exc))
        if sys.stderr is not None:
            print(exc, file=sys.stderr)
        return 2
    setup_logging(settings)
    log = logging.getLogger("vn_parcel_bot")
    try:
        with SingleInstanceLock(settings.db_path.parent / "bot.lock"):
            app = build_application(settings)
            app.run_polling(allowed_updates=Update.ALL_TYPES)
            return int(app.bot_data.get("exit_code", 0))
    except SingleInstanceError:
        log.warning("another instance is running; exiting")
        return 0
    except Exception:
        log.exception("fatal error")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
