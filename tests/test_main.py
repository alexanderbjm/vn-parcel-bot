import logging

import pytest

from vn_parcel_bot import __main__ as entry
from vn_parcel_bot.single_instance import SingleInstanceLock

ENV_KEYS = (
    "TELEGRAM_BOT_TOKEN",
    "ADMIN_TELEGRAM_ID",
    "LOG_DIR",
    "DB_PATH",
    "TELEGRAM_PROXY_URL",
    "QUIET_HOURS",
)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    for handler in root.handlers:
        if handler not in handlers:
            handler.close()
    root.handlers[:] = handlers
    root.setLevel(level)


def test_config_error_returns_2_and_writes_log(tmp_path):
    assert entry.main() == 2
    log_file = tmp_path / "logs" / "startup-error.log"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "TELEGRAM_BOT_TOKEN" in content


def test_second_instance_returns_0(tmp_path, monkeypatch, valid_env):
    for key, value in valid_env.items():
        monkeypatch.setenv(key, value)

    def must_not_build(settings):
        raise AssertionError("build_application must not run while the lock is held")

    monkeypatch.setattr(entry, "build_application", must_not_build)
    with SingleInstanceLock(tmp_path / "data" / "bot.lock"):
        assert entry.main() == 0
