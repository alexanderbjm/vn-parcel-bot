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
