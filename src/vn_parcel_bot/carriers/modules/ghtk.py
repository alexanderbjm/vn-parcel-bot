from vn_parcel_bot.carriers.api import PRIORITY_PREFIXED, CarrierModule, Rule

MODULE = CarrierModule(
    code="ghtk",
    display_name="GHTK",
    order=90,
    rules=(
        Rule(r"S\d{5,10}(\.[0-9A-Z]{1,12}){1,4}", PRIORITY_PREFIXED),
        Rule(r"GHTK[0-9A-Z]{6,16}", PRIORITY_PREFIXED),
    ),
    link_template="https://i.ghtk.vn/{code}",
    examples=(("S1234567.MB12.D5.123456789", True), ("GHTK0012345678", True)),
)
