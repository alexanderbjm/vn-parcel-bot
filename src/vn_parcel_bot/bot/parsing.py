from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from vn_parcel_bot.carrier_catalog import CarrierCode, needs_phone, parse_carrier_alias
from vn_parcel_bot.tracking_codes import (
    detect_carriers,
    extract_codes,
    is_valid_last4,
    normalize_code,
)


def parse_track_args(args: Sequence[str]) -> tuple[str, str | None, CarrierCode | None] | None:
    parts = [arg for arg in args if arg.strip()]
    if not parts:
        return None
    carrier = parse_carrier_alias(parts[-1]) if len(parts) >= 2 else None
    if carrier is not None:
        parts = parts[:-1]
    last4 = None
    if len(parts) >= 2 and is_valid_last4(parts[-1]):
        if carrier is not None:
            wants_phone = needs_phone(carrier)
        else:
            rest = normalize_code("".join(parts[:-1]))
            wants_phone = any(needs_phone(code) for code in detect_carriers(rest))
        if wants_phone:
            last4 = parts[-1]
            parts = parts[:-1]
    code = normalize_code("".join(parts))
    return (code, last4, carrier) if code else None


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
