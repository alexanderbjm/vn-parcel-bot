import logging
import sys
from logging.handlers import RotatingFileHandler

from vn_parcel_bot.config import Settings

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_OWNED = "_vn_parcel_bot_handler"


class RedactTokenFilter(logging.Filter):
    def __init__(self, secret: str) -> None:
        super().__init__()
        self._secret = secret

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._secret:
            return True
        message = record.getMessage()
        if self._secret in message:
            record.msg = message.replace(self._secret, "***")
            record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text and self._secret in record.exc_text:
            record.exc_text = record.exc_text.replace(self._secret, "***")
        if record.stack_info and self._secret in record.stack_info:
            record.stack_info = record.stack_info.replace(self._secret, "***")
        return True


def setup_logging(settings: Settings) -> None:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        if getattr(handler, _OWNED, False):
            handler.close()

    handlers: list[logging.Handler] = [
        RotatingFileHandler(
            settings.log_dir / "bot.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8"
        )
    ]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler(sys.stderr))

    formatter = logging.Formatter(LOG_FORMAT)
    redact = RedactTokenFilter(settings.telegram_bot_token)
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(redact)
        setattr(handler, _OWNED, True)
        root.addHandler(handler)

    root.setLevel(settings.log_level)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
