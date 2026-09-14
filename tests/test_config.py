from datetime import timedelta
from pathlib import Path

import pytest

from vn_parcel_bot.config import ConfigError, Settings


def test_minimal_env_uses_defaults(valid_env):
    s = Settings.from_env(valid_env)
    assert s.telegram_bot_token == valid_env["TELEGRAM_BOT_TOKEN"]
    assert s.admin_telegram_id == 111
    assert s.poll_interval_minutes == 20
    assert s.request_delay_seconds == 3.0
    assert s.http_timeout_seconds == 15.0
    assert s.db_path == Path("data/bot.sqlite3")
    assert s.log_dir == Path("logs")
    assert s.log_level == "INFO"
    assert s.timezone == "Asia/Ho_Chi_Minh"
    assert s.quiet_hours == (22, 7)
    assert s.max_parcels_per_user == 30
    assert s.telegram_proxy_url is None
    assert s.anthropic_api_key is None
    assert s.anthropic_model == "claude-3-5-haiku-20241022"
    assert s.poll_interval == timedelta(minutes=20)


def test_anthropic_settings_configured(valid_env):
    s = Settings.from_env(
        {
            **valid_env,
            "ANTHROPIC_API_KEY": "sk-ant-key-123",
            "ANTHROPIC_MODEL": "claude-3-5-sonnet-20241022",
        }
    )
    assert s.anthropic_api_key == "sk-ant-key-123"
    assert s.anthropic_model == "claude-3-5-sonnet-20241022"


def test_missing_required_reports_both():
    with pytest.raises(ConfigError) as exc:
        Settings.from_env({})
    assert "TELEGRAM_BOT_TOKEN" in str(exc.value)
    assert "ADMIN_TELEGRAM_ID" in str(exc.value)


def test_empty_string_counts_as_unset():
    with pytest.raises(ConfigError) as exc:
        Settings.from_env({"TELEGRAM_BOT_TOKEN": "", "ADMIN_TELEGRAM_ID": ""})
    assert "TELEGRAM_BOT_TOKEN" in str(exc.value)


def test_invalid_token_format(valid_env):
    with pytest.raises(ConfigError, match="TELEGRAM_BOT_TOKEN"):
        Settings.from_env({**valid_env, "TELEGRAM_BOT_TOKEN": "abc"})


@pytest.mark.parametrize("value", ["x", "0", "-5"])
def test_admin_id_must_be_positive_int(valid_env, value):
    with pytest.raises(ConfigError, match="ADMIN_TELEGRAM_ID"):
        Settings.from_env({**valid_env, "ADMIN_TELEGRAM_ID": value})


@pytest.mark.parametrize("value", ["4", "241", "abc"])
def test_poll_interval_rejected(valid_env, value):
    with pytest.raises(ConfigError, match="POLL_INTERVAL_MINUTES"):
        Settings.from_env({**valid_env, "POLL_INTERVAL_MINUTES": value})


@pytest.mark.parametrize("value", ["5", "240"])
def test_poll_interval_accepted(valid_env, value):
    assert Settings.from_env(
        {**valid_env, "POLL_INTERVAL_MINUTES": value}
    ).poll_interval_minutes == int(value)


def test_delay_timeout_and_max_parcels_bounds(valid_env):
    for key, bad in [
        ("REQUEST_DELAY_SECONDS", "61"),
        ("REQUEST_DELAY_SECONDS", "-1"),
        ("HTTP_TIMEOUT_SECONDS", "0"),
        ("HTTP_TIMEOUT_SECONDS", "121"),
        ("MAX_PARCELS_PER_USER", "0"),
        ("MAX_PARCELS_PER_USER", "201"),
    ]:
        with pytest.raises(ConfigError, match=key):
            Settings.from_env({**valid_env, key: bad})
    s = Settings.from_env(
        {
            **valid_env,
            "REQUEST_DELAY_SECONDS": "0",
            "HTTP_TIMEOUT_SECONDS": "0.5",
            "MAX_PARCELS_PER_USER": "200",
        }
    )
    assert (s.request_delay_seconds, s.http_timeout_seconds, s.max_parcels_per_user) == (
        0.0,
        0.5,
        200,
    )


def test_quiet_hours_variants(valid_env):
    assert Settings.from_env({**valid_env, "QUIET_HOURS": "22-7"}).quiet_hours == (22, 7)
    assert Settings.from_env({**valid_env, "QUIET_HOURS": ""}).quiet_hours is None
    for bad in ["25-7", "7-7", "abc"]:
        with pytest.raises(ConfigError, match="QUIET_HOURS"):
            Settings.from_env({**valid_env, "QUIET_HOURS": bad})


def test_invalid_timezone_rejected(valid_env):
    with pytest.raises(ConfigError, match="TIMEZONE"):
        Settings.from_env({**valid_env, "TIMEZONE": "Mars/Base"})


def test_tz_property_loads_ho_chi_minh(settings):
    assert settings.tz.key == "Asia/Ho_Chi_Minh"


def test_proxy_scheme_validation(valid_env):
    ok = Settings.from_env({**valid_env, "TELEGRAM_PROXY_URL": "socks5h://127.0.0.1:1080"})
    assert ok.telegram_proxy_url == "socks5h://127.0.0.1:1080"
    assert Settings.from_env({**valid_env, "TELEGRAM_PROXY_URL": ""}).telegram_proxy_url is None
    with pytest.raises(ConfigError, match="TELEGRAM_PROXY_URL"):
        Settings.from_env({**valid_env, "TELEGRAM_PROXY_URL": "ftp://x"})


def test_log_level_normalized(valid_env):
    assert Settings.from_env({**valid_env, "LOG_LEVEL": "debug"}).log_level == "DEBUG"
    with pytest.raises(ConfigError, match="LOG_LEVEL"):
        Settings.from_env({**valid_env, "LOG_LEVEL": "LOUD"})


def test_paths_converted(valid_env):
    s = Settings.from_env({**valid_env, "DB_PATH": "x/y.db", "LOG_DIR": "z"})
    assert s.db_path == Path("x/y.db")
    assert s.log_dir == Path("z")


def test_collects_multiple_errors(valid_env):
    with pytest.raises(ConfigError) as exc:
        Settings.from_env({**valid_env, "POLL_INTERVAL_MINUTES": "1", "LOG_LEVEL": "LOUD"})
    assert "POLL_INTERVAL_MINUTES" in str(exc.value)
    assert "LOG_LEVEL" in str(exc.value)
