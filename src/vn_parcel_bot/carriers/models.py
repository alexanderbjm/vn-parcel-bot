import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

import httpx

CarrierCode = str
ErrorReason = Literal["network", "blocked", "http_status", "parse"]


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


@dataclass(frozen=True)
class TrackingEvent:
    time: datetime
    description: str
    location: str | None = None
    raw_status: str | None = None

    def __post_init__(self) -> None:
        if self.time.tzinfo is None or self.time.utcoffset() is None:
            raise ValueError("TrackingEvent.time must be timezone-aware")

    @property
    def key(self) -> str:
        utc = self.time.astimezone(UTC).replace(microsecond=0).isoformat()
        raw = f"{utc}|{_norm(self.description)}|{_norm(self.location or '')}"
        return hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


@dataclass(frozen=True)
class TrackingResult:
    carrier: CarrierCode
    tracking_number: str
    found: bool
    events: tuple[TrackingEvent, ...] = ()
    delivered: bool = False
    returned: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "events", tuple(sorted(self.events, key=lambda e: e.time)))

    @property
    def latest(self) -> TrackingEvent | None:
        return self.events[-1] if self.events else None


class CarrierError(Exception):
    def __init__(self, carrier: CarrierCode, reason: ErrorReason, detail: str = "") -> None:
        super().__init__(f"{carrier}:{reason}: {detail}")
        self.carrier = carrier
        self.reason = reason
        self.detail = detail


class Carrier(Protocol):
    code: CarrierCode
    display_name: str
    needs_phone: bool

    async def fetch(
        self, http: httpx.AsyncClient, tracking_number: str, phone_last4: str | None = None
    ) -> TrackingResult: ...
