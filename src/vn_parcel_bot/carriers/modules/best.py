from vn_parcel_bot.carriers.api import (
    PRIORITY_NUMERIC,
    PRIORITY_PREFIXED,
    PRIORITY_SHARED_NUMERIC,
    CarrierModule,
    Rule,
)

MODULE = CarrierModule(
    code="best",
    display_name="BEST Express",
    order=70,
    rules=(
        Rule(r"BEST[A-Z]{0,6}\d{8,16}VN[A-Z]{0,3}", PRIORITY_PREFIXED),
        Rule(r"\d{13}", PRIORITY_NUMERIC),
        Rule(r"\d{12}", PRIORITY_SHARED_NUMERIC, rank=1),
    ),
    link_template="https://www.best-inc.vn/track?bills={code}",
    examples=(("BESTMP0000000001VNA", True), ("8410000726470", True), ("841000072647", True)),
)
