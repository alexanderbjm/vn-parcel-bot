import os

from vn_parcel_bot.carriers.api import (
    PRIORITY_NUMERIC,
    PRIORITY_PREFIXED,
    PRIORITY_SHARED_NUMERIC,
    CarrierModule,
    Rule,
)
from vn_parcel_bot.carriers.models import Carrier
from vn_parcel_bot.carriers.seventeen_track import SeventeenTrackCarrier


def build_best_client() -> Carrier | None:
    api_key = os.environ.get("SEVENTEEN_TRACK_KEY")
    if not api_key or not api_key.strip():
        return None
    return SeventeenTrackCarrier(
        carrier_code="best",
        display_name="🌟 BEST Express",
        seventeen_carrier_id=101194,
        api_key=api_key.strip(),
        needs_phone=True,
    )


MODULE = CarrierModule(
    code="best",
    display_name="🌟 BEST Express",
    order=70,
    needs_phone=True,
    rules=(
        Rule(r"BEST[A-Z]{0,6}\d{8,16}(?:VN[A-Z]{0,3})?", PRIORITY_PREFIXED),
        Rule(r"\d{13}", PRIORITY_NUMERIC),
        Rule(r"\d{12}", PRIORITY_SHARED_NUMERIC, rank=1),
    ),
    link_template="https://www.best-inc.vn/track?bills={code}",
    examples=(
        ("BESTMP0000000001VNA", True),
        ("BEST0000000001", True),
        ("8410000726470", True),
        ("841000072647", True),
    ),
    build_client=build_best_client,
)
