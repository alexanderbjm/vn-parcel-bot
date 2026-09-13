import pytest

from vn_parcel_bot.config import Settings


@pytest.fixture
def valid_env() -> dict[str, str]:
    return {"TELEGRAM_BOT_TOKEN": "123456789:" + "A" * 35, "ADMIN_TELEGRAM_ID": "111"}


@pytest.fixture
def settings(tmp_path, valid_env) -> Settings:
    return Settings.from_env(
        {**valid_env, "DB_PATH": str(tmp_path / "bot.sqlite3"), "LOG_DIR": str(tmp_path / "logs")}
    )
