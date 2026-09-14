from vn_parcel_bot.carrier_catalog import CarrierCode
from vn_parcel_bot.carriers.models import Carrier
from vn_parcel_bot.carriers.modules.cainiao import CainiaoCarrier
from vn_parcel_bot.carriers.modules.fourpx import FourPxCarrier
from vn_parcel_bot.carriers.modules.ghn import GhnCarrier
from vn_parcel_bot.carriers.modules.jt import JtCarrier
from vn_parcel_bot.carriers.modules.ninjavan import NinjaVanCarrier
from vn_parcel_bot.carriers.modules.spx import SpxCarrier

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
