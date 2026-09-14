from vn_parcel_bot.carriers.api import PRIORITY_SHARED_NUMERIC, CarrierModule, Rule

MODULE = CarrierModule(
    code="viettelpost",
    display_name="Viettel Post",
    order=100,
    rules=(Rule(r"\d{12}", PRIORITY_SHARED_NUMERIC, rank=2),),
    link_template="https://viettelpost.com.vn/tra-cuu-hanh-trinh-don/",
    examples=(("841000072647", True),),
)
