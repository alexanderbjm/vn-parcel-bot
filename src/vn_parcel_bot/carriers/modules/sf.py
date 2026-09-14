from vn_parcel_bot.carriers.api import PRIORITY_PREFIXED, CarrierModule, Rule

MODULE = CarrierModule(
    code="sf",
    display_name="SF Express",
    order=130,
    rules=(Rule(r"SF\d{13}", PRIORITY_PREFIXED),),
    link_template="https://www.sf-express.com/chn/en/waybill/list",
    examples=(("SF0000000000001", True),),
)
