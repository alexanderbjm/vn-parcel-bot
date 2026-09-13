from vn_parcel_bot.carrier_catalog import CarrierCode
from vn_parcel_bot.carriers.cainiao import CainiaoCarrier
from vn_parcel_bot.carriers.fourpx import FourPxCarrier
from vn_parcel_bot.carriers.ghn import GhnCarrier
from vn_parcel_bot.carriers.jt import JtCarrier
from vn_parcel_bot.carriers.models import Carrier
from vn_parcel_bot.carriers.ninjavan import NinjaVanCarrier
from vn_parcel_bot.carriers.spx import SpxCarrier

CARRIERS: dict[CarrierCode, Carrier] = {
    "spx": SpxCarrier(),
    "jt": JtCarrier(),
    "cainiao": CainiaoCarrier(),
    "fourpx": FourPxCarrier(),
    "ninjavan": NinjaVanCarrier(),
    "ghn": GhnCarrier(),
}


def get_carrier(code: CarrierCode) -> Carrier:
    return CARRIERS[code]
