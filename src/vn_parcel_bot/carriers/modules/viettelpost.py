from vn_parcel_bot.carriers.api import (
    PRIORITY_PREFIXED,
    PRIORITY_SHARED_NUMERIC,
    CarrierModule,
    Rule,
)

MODULE = CarrierModule(
    code="viettelpost",
    display_name="🟥 Viettel Post",
    order=100,
    rules=(
        Rule(r"VTP[0-9A-Z]{6,14}", PRIORITY_PREFIXED),
        Rule(r"\d{12}", PRIORITY_SHARED_NUMERIC, rank=2),
    ),
    link_template="https://viettelpost.com.vn/tra-cuu-hanh-trinh-don/",
    examples=(("841000072647", True), ("VTP0000000001", True)),
)
