from vn_parcel_bot.carriers.api import PRIORITY_PREFIXED, CarrierModule, Rule

MODULE = CarrierModule(
    code="vnpost",
    display_name="VNPost",
    order=110,
    rules=(Rule(r"[A-Z]{2}\d{9}VN", PRIORITY_PREFIXED),),
    link_template=(
        "https://vnpost.vn/vi/ca-nhan/chuyen-phat/chuyen-phat-trong-nuoc"
        "#!?tab=tra-cuu-hanh-trinh&code={code}"
    ),
    examples=(("EB123456789VN", True),),
)
