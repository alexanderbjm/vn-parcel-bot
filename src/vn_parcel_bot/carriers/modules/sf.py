import os

from vn_parcel_bot.carriers.api import PRIORITY_PREFIXED, CarrierModule, Rule
from vn_parcel_bot.carriers.models import Carrier
from vn_parcel_bot.carriers.seventeen_track import SeventeenTrackCarrier


def build_sf_client() -> Carrier | None:
    api_key = os.environ.get("SEVENTEEN_TRACK_KEY")
    if not api_key or not api_key.strip():
        return None
    return SeventeenTrackCarrier(
        carrier_code="sf",
        display_name="SF Express",
        seventeen_carrier_id=100012,
        api_key=api_key.strip(),
    )


MODULE = CarrierModule(
    code="sf",
    display_name="SF Express",
    order=130,
    rules=(Rule(r"SF\d{12,15}", PRIORITY_PREFIXED),),
    link_template="https://www.sf-express.com/chn/en/waybill/list",
    examples=(("SF0000000000001", True), ("SF123456789012", True)),
    build_client=build_sf_client,
)
