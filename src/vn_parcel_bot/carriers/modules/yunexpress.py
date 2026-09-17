from vn_parcel_bot.carriers.api import PRIORITY_PREFIXED, CarrierModule, Rule

MODULE = CarrierModule(
    code="yunexpress",
    display_name="☁️ YunExpress",
    order=80,
    rules=(Rule(r"YT\d{16,18}", PRIORITY_PREFIXED),),
    link_template="https://www.yuntrack.com/parcelTracking?id={code}",
    examples=(("YT1234567890123456", True), ("YT0000000000001", False)),
)
