import re
from collections.abc import Collection
from datetime import timedelta, timezone, tzinfo
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from vn_parcel_bot.carrier_catalog import CarrierCode
from vn_parcel_bot.carriers.models import CarrierError

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

_OFFSET_RE = re.compile(r"^(?:GMT|UTC)?\s*([+-]?)(\d{1,2})(?::?(\d{2}))?$")
_CHALLENGE_WORDS = ("captcha", "cf-challenge", "x5sec", "punish")


async def request(
    http: httpx.AsyncClient,
    carrier: CarrierCode,
    method: str,
    url: str,
    *,
    not_found_statuses: Collection[int] = (),
    **kwargs: Any,
) -> httpx.Response:
    try:
        response = await http.request(method, url, **kwargs)
    except httpx.TransportError as exc:
        raise CarrierError(carrier, "network", type(exc).__name__) from exc
    status = response.status_code
    if status in not_found_statuses:
        return response
    if status in (403, 429):
        raise CarrierError(carrier, "blocked", str(status))
    if not 200 <= status < 300:
        raise CarrierError(carrier, "http_status", str(status))
    content_type = response.headers.get("content-type", "").lower()
    if "json" not in content_type and looks_like_challenge(response.text):
        raise CarrierError(carrier, "blocked", "challenge page")
    return response


def json_body(carrier: CarrierCode, response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        if response.text.lstrip().startswith("<"):
            raise CarrierError(carrier, "blocked", "html instead of json") from exc
        raise CarrierError(carrier, "parse", "invalid json") from exc


def looks_like_challenge(text: str) -> bool:
    lowered = text.casefold()
    if any(word in lowered for word in _CHALLENGE_WORDS):
        return True
    return "document.cookie" in lowered and "location.reload" in lowered


def parse_gmt_offset(value: object, default: tzinfo) -> tzinfo:
    if value is None or isinstance(value, bool):
        return default
    match = _OFFSET_RE.match(str(value).strip().upper())
    if not match:
        return default
    hours, minutes = int(match.group(2)), int(match.group(3) or 0)
    if hours > 14 or minutes >= 60:
        return default
    sign = -1 if match.group(1) == "-" else 1
    return timezone(sign * timedelta(hours=hours, minutes=minutes))


def clean_text(value: object) -> str:
    return " ".join(str(value).split())
