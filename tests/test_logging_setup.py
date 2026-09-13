import logging
import sys

import pytest

from vn_parcel_bot.logging_setup import RedactTokenFilter, setup_logging


@pytest.fixture(autouse=True)
def restore_root_logging():
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    for handler in root.handlers:
        if handler not in handlers:
            handler.close()
    root.handlers[:] = handlers
    root.setLevel(level)


def test_redact_filter_masks_secret_in_message_and_args():
    token = "123456789:" + "B" * 35
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "url bot%s/getMe", (token,), None)
    assert RedactTokenFilter(token).filter(record) is True
    output = logging.Formatter("%(message)s").format(record)
    assert "***" in output
    assert token not in output


def test_setup_logging_creates_log_file(settings):
    setup_logging(settings)
    logging.getLogger("vn_parcel_bot.test").info("hello log file")
    for handler in logging.getLogger().handlers:
        handler.flush()
    content = (settings.log_dir / "bot.log").read_text(encoding="utf-8")
    assert "hello log file" in content


def test_httpx_loggers_quiet(settings):
    setup_logging(settings)
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


def test_setup_logging_is_idempotent(settings):
    setup_logging(settings)
    setup_logging(settings)
    expected = 2 if sys.stderr is not None else 1
    assert len(logging.getLogger().handlers) == expected


def test_token_never_written(settings):
    setup_logging(settings)
    logging.getLogger("vn_parcel_bot.test").warning(f"token {settings.telegram_bot_token}")
    for handler in logging.getLogger().handlers:
        handler.flush()
    content = (settings.log_dir / "bot.log").read_text(encoding="utf-8")
    assert settings.telegram_bot_token not in content
    assert "token ***" in content
