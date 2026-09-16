import os

import pytest

from vn_parcel_bot.config import Settings


@pytest.fixture(scope="session", autouse=True)
def _no_ambient_seventeen_track_key():
    """Keep the surrounding shell out of the carrier registry.

    `best.py`, `sf.py` and `jt.py` read SEVENTEEN_TRACK_KEY straight from os.environ, so a key in
    the developer's shell — or a .env loaded into it — silently turns BEST and SF from link-only
    carriers into tracked ones, and lets the cross-border J&T tests reach the live 17TRACK API.
    Session scope so the module-scoped registry snapshots are built without it too.
    """
    saved = os.environ.pop("SEVENTEEN_TRACK_KEY", None)
    yield
    if saved is not None:
        os.environ["SEVENTEEN_TRACK_KEY"] = saved


@pytest.fixture
def valid_env() -> dict[str, str]:
    return {"TELEGRAM_BOT_TOKEN": "123456789:" + "A" * 35, "ADMIN_TELEGRAM_ID": "111"}


@pytest.fixture
def settings(tmp_path, valid_env) -> Settings:
    return Settings.from_env(
        {**valid_env, "DB_PATH": str(tmp_path / "bot.sqlite3"), "LOG_DIR": str(tmp_path / "logs")}
    )
