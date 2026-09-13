from dataclasses import dataclass
from typing import Literal

from vn_parcel_bot.carrier_catalog import CarrierCode
from vn_parcel_bot.carriers.models import CarrierError, TrackingResult
from vn_parcel_bot.db.repo import Parcel

AddKind = Literal[
    "added", "needs_phone", "link_only", "duplicate", "limit", "invalid_code", "invalid_phone"
]


@dataclass(frozen=True)
class AddOutcome:
    kind: AddKind
    code: str | None = None
    parcel: Parcel | None = None
    result: TrackingResult | None = None
    error: CarrierError | None = None
    candidates: tuple[CarrierCode, ...] = ()
    link_carriers: tuple[CarrierCode, ...] = ()
