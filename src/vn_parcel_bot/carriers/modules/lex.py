from vn_parcel_bot.carriers.api import PRIORITY_PREFIXED, CarrierModule, Rule

MODULE = CarrierModule(
    code="lex",
    display_name="💙 LEX VN",
    order=120,
    rules=(Rule(r"(LEXVN|LXVN|LVS)[0-9A-Z]{6,20}", PRIORITY_PREFIXED),),
    link_template="https://logistics.lazada.vn/",
    examples=(("LEXVN00123456", True),),
)
