import re
import urllib.parse
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from vn_parcel_bot.carriers.registry import current_snapshot
from vn_parcel_bot.tracking_codes import (
    detect_carriers,
    extract_codes,
    is_order_number,
    is_seller_fleet,
    is_valid_last4,
    normalize_code,
)

# A Google Maps place link's pin ("!3d<lat>!4d<lon>"), then a "lat, lon" pair anywhere in the text
# (plain coordinates, "@lat,lon", "q=lat,lon"). Decimals are required so codes never match.
_MAPS_PIN = re.compile(r"!3d(-?\d{1,2}(?:\.\d+)?)!4d(-?\d{1,3}(?:\.\d+)?)")
_COORDINATE_PAIR = re.compile(r"(?<![\d.])(-?\d{1,2}\.\d+)\s*(?:,\s*|\s+)(-?\d{1,3}\.\d+)(?![\d.])")


def parse_coordinates(text: str) -> tuple[float, float] | None:
    """Latitude and longitude from pasted coordinates or a Google Maps link, read locally."""
    unquoted = urllib.parse.unquote(text)
    match = _MAPS_PIN.search(unquoted) or _COORDINATE_PAIR.search(unquoted)
    if match is None:
        return None
    lat, lon = float(match.group(1)), float(match.group(2))
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def parse_track_args(args: Sequence[str]) -> tuple[str, str | None] | None:
    parts = [arg for arg in args if arg.strip()]
    if not parts:
        return None
    last4 = None
    if len(parts) >= 2 and is_valid_last4(parts[-1]):
        rest = normalize_code("".join(parts[:-1]))
        if any(current_snapshot().needs_phone(carrier) for carrier in detect_carriers(rest)):
            last4 = parts[-1]
            parts = parts[:-1]
    joined = normalize_code("".join(parts))
    if detect_carriers(joined) or is_order_number(joined) or is_seller_fleet(joined):
        return joined, last4
    codes = extract_codes(" ".join(parts))
    if codes:
        return codes[0], last4
    return (joined, last4) if joined else None


def parse_ref_and_text(args: Sequence[str]) -> tuple[str, str | None] | None:
    if not args:
        return None
    return args[0], " ".join(args[1:]).strip() or None


@dataclass(frozen=True)
class TextRoute:
    kind: Literal["phone_for_pending", "codes", "invalid_phone", "unknown"]
    codes: tuple[str, ...] = ()
    last4: str | None = None


def route_text(text: str, has_pending: bool) -> TextRoute:
    stripped = text.strip()
    if has_pending and is_valid_last4(stripped):
        return TextRoute("phone_for_pending", last4=stripped)
    codes = extract_codes(text)
    if codes:
        return TextRoute("codes", codes=tuple(codes))
    return TextRoute("invalid_phone" if has_pending else "unknown")
