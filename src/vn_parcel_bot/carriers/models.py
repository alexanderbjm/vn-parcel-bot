from typing import Literal

from vn_parcel_bot.carrier_catalog import CarrierCode

ErrorReason = Literal["network", "blocked", "http_status", "parse"]


class CarrierError(Exception):
    def __init__(self, carrier: CarrierCode, reason: ErrorReason, detail: str = "") -> None:
        super().__init__(f"{carrier}:{reason}: {detail}")
        self.carrier = carrier
        self.reason = reason
        self.detail = detail
