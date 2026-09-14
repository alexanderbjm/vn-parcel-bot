import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import time, timedelta
from pathlib import Path
from typing import Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_TOKEN_RE = re.compile(r"^\d+:[A-Za-z0-9_-]{30,}$")
_QUIET_HOURS_RE = re.compile(r"^(\d{1,2})-(\d{1,2})$")
_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
_PROXY_SCHEMES = ("http://", "https://", "socks5://", "socks5h://")
_VISION_ENGINES = ("claude_code", "api")
_DIGEST_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
DEFAULT_DIGEST_TIMES = (time(7), time(12), time(19), time(22))


class ConfigError(Exception):
    pass


def _get(env: Mapping[str, str], key: str) -> str | None:
    value = env.get(key)
    if value is None or not value.strip():
        return None
    return value.strip()


def _int(
    env: Mapping[str, str], key: str, default: int, low: int, high: int, errors: list[str]
) -> int:
    raw = _get(env, key)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        errors.append(f"{key} must be an integer between {low} and {high}")
        return default
    if not low <= value <= high:
        errors.append(f"{key} must be between {low} and {high}")
    return value


def _float(
    env: Mapping[str, str],
    key: str,
    default: float,
    low: float,
    high: float,
    errors: list[str],
    *,
    low_exclusive: bool = False,
) -> float:
    raw = _get(env, key)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        errors.append(f"{key} must be a number")
        return default
    too_low = value <= low if low_exclusive else value < low
    if too_low or value > high:
        bound = ">" if low_exclusive else ">="
        errors.append(f"{key} must be {bound} {low:g} and <= {high:g}")
    return value


def default_claude_code_path() -> str | None:
    found = shutil.which("claude")
    if found:
        return found
    fallback = Path.home() / ".local" / "bin" / "claude.exe"
    return str(fallback) if fallback.is_file() else None


def _digest_times(env: Mapping[str, str], errors: list[str]) -> tuple[time, ...]:
    if "DIGEST_TIMES" not in env:
        return DEFAULT_DIGEST_TIMES
    raw = env["DIGEST_TIMES"].strip()
    if not raw:
        return ()
    slots: set[time] = set()
    for part in raw.split(","):
        match = _DIGEST_TIME_RE.match(part.strip())
        hour, minute = (int(match.group(1)), int(match.group(2))) if match else (-1, -1)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            errors.append(
                "DIGEST_TIMES must be comma-separated HH:MM times (00:00..23:59) or empty"
            )
            return DEFAULT_DIGEST_TIMES
        slots.add(time(hour, minute))
    return tuple(sorted(slots))


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    admin_telegram_id: int
    poll_interval_minutes: int = 20
    request_delay_seconds: float = 3.0
    http_timeout_seconds: float = 15.0
    db_path: Path = Path("data/bot.sqlite3")
    log_dir: Path = Path("logs")
    log_level: str = "INFO"
    timezone: str = "Asia/Ho_Chi_Minh"
    quiet_hours: tuple[int, int] | None = (22, 7)
    max_parcels_per_user: int = 30
    telegram_proxy_url: str | None = None
    digest_times: tuple[time, ...] = DEFAULT_DIGEST_TIMES
    vision_engine: str = "claude_code"
    claude_code_path: str | None = None
    vision_model: str = "haiku"
    vision_timeout_seconds: int = 90
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-haiku-4-5-20251001"
    anthropic_workspace_id: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Self:
        errors: list[str] = []

        token = _get(env, "TELEGRAM_BOT_TOKEN")
        if token is None:
            errors.append("TELEGRAM_BOT_TOKEN is required")
        elif not _TOKEN_RE.match(token):
            errors.append("TELEGRAM_BOT_TOKEN has an invalid format")

        admin_raw = _get(env, "ADMIN_TELEGRAM_ID")
        admin_id = 0
        if admin_raw is None:
            errors.append("ADMIN_TELEGRAM_ID is required")
        else:
            try:
                admin_id = int(admin_raw)
            except ValueError:
                admin_id = 0
            if admin_id <= 0:
                errors.append("ADMIN_TELEGRAM_ID must be a positive integer")

        poll = _int(env, "POLL_INTERVAL_MINUTES", 20, 5, 240, errors)
        delay = _float(env, "REQUEST_DELAY_SECONDS", 3.0, 0, 60, errors)
        timeout = _float(env, "HTTP_TIMEOUT_SECONDS", 15.0, 0, 120, errors, low_exclusive=True)
        max_parcels = _int(env, "MAX_PARCELS_PER_USER", 30, 1, 200, errors)

        log_level = (_get(env, "LOG_LEVEL") or "INFO").upper()
        if log_level not in _LOG_LEVELS:
            errors.append(f"LOG_LEVEL must be one of {', '.join(_LOG_LEVELS)}")

        timezone = _get(env, "TIMEZONE") or "Asia/Ho_Chi_Minh"
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError):
            errors.append(f"TIMEZONE {timezone!r} is not a known time zone")

        quiet_hours: tuple[int, int] | None = (22, 7)
        if "QUIET_HOURS" in env:
            raw = env["QUIET_HOURS"].strip()
            if not raw:
                quiet_hours = None
            else:
                match = _QUIET_HOURS_RE.match(raw)
                start, end = (int(match.group(1)), int(match.group(2))) if match else (-1, -1)
                if not (0 <= start <= 23 and 0 <= end <= 23) or start == end:
                    errors.append(
                        "QUIET_HOURS must look like 22-7 (hours 0..23, different) or be empty"
                    )
                else:
                    quiet_hours = (start, end)

        proxy = _get(env, "TELEGRAM_PROXY_URL")
        if proxy is not None and not (
            proxy.startswith(_PROXY_SCHEMES) and len(proxy.split("://", 1)[1]) > 0
        ):
            errors.append(
                "TELEGRAM_PROXY_URL must start with http://, https://, socks5:// or socks5h://"
            )

        vision_engine = (_get(env, "VISION_ENGINE") or "claude_code").lower()
        if vision_engine not in _VISION_ENGINES:
            errors.append(f"VISION_ENGINE must be one of {', '.join(_VISION_ENGINES)}")
        vision_timeout = _int(env, "VISION_TIMEOUT_SECONDS", 90, 10, 300, errors)
        digest_times = _digest_times(env, errors)

        if errors:
            raise ConfigError("Invalid configuration:\n- " + "\n- ".join(errors))

        return cls(
            telegram_bot_token=token or "",
            admin_telegram_id=admin_id,
            poll_interval_minutes=poll,
            request_delay_seconds=delay,
            http_timeout_seconds=timeout,
            db_path=Path(_get(env, "DB_PATH") or "data/bot.sqlite3"),
            log_dir=Path(_get(env, "LOG_DIR") or "logs"),
            log_level=log_level,
            timezone=timezone,
            quiet_hours=quiet_hours,
            max_parcels_per_user=max_parcels,
            telegram_proxy_url=proxy,
            digest_times=digest_times,
            vision_engine=vision_engine,
            claude_code_path=_get(env, "CLAUDE_CODE_PATH") or default_claude_code_path(),
            vision_model=_get(env, "VISION_MODEL") or "haiku",
            vision_timeout_seconds=vision_timeout,
            anthropic_api_key=_get(env, "ANTHROPIC_API_KEY"),
            anthropic_model=_get(env, "ANTHROPIC_MODEL") or "claude-haiku-4-5-20251001",
            anthropic_workspace_id=_get(env, "ANTHROPIC_WORKSPACE_ID"),
        )

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def poll_interval(self) -> timedelta:
        return timedelta(minutes=self.poll_interval_minutes)
