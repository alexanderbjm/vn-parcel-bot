import urllib.parse
from dataclasses import dataclass
from typing import Literal

CarrierCode = Literal[
    "spx",
    "jt",
    "cainiao",
    "fourpx",
    "ninjavan",
    "ghn",
    "best",
    "yunexpress",
    "ghtk",
    "viettelpost",
    "vnpost",
    "lex",
]


@dataclass(frozen=True)
class CarrierInfo:
    code: CarrierCode
    display_name: str
    tracked: bool
    needs_phone: bool
    link_template: str | None


CATALOG: dict[CarrierCode, CarrierInfo] = {
    info.code: info
    for info in (
        CarrierInfo("spx", "SPX", True, False, None),
        CarrierInfo("jt", "J&T", True, True, None),
        CarrierInfo("cainiao", "Cainiao", True, False, None),
        CarrierInfo("fourpx", "4PX", True, False, None),
        CarrierInfo("ninjavan", "Ninja Van", True, False, None),
        CarrierInfo("ghn", "GHN", True, True, None),
        CarrierInfo(
            "best", "BEST Express", False, False, "https://www.best-inc.vn/track?bills={code}"
        ),
        CarrierInfo(
            "yunexpress",
            "YunExpress",
            False,
            False,
            "https://www.yuntrack.com/parcelTracking?id={code}",
        ),
        CarrierInfo("ghtk", "GHTK", False, False, "https://i.ghtk.vn/{code}"),
        CarrierInfo(
            "viettelpost",
            "Viettel Post",
            False,
            False,
            "https://viettelpost.com.vn/tra-cuu-hanh-trinh-don/",
        ),
        CarrierInfo(
            "vnpost",
            "VNPost",
            False,
            False,
            "https://vnpost.vn/vi/ca-nhan/chuyen-phat/chuyen-phat-trong-nuoc"
            "#!?tab=tra-cuu-hanh-trinh&code={code}",
        ),
        CarrierInfo("lex", "LEX VN", False, False, "https://logistics.lazada.vn/"),
    )
}

TRACKED: tuple[CarrierCode, ...] = tuple(code for code, info in CATALOG.items() if info.tracked)

SEVENTEEN_TRACK_TEMPLATE = "https://t.17track.net/vi#nums={code}"


def is_tracked(carrier: CarrierCode) -> bool:
    return CATALOG[carrier].tracked


def needs_phone(carrier: CarrierCode) -> bool:
    return CATALOG[carrier].needs_phone


def _fill(template: str, code: str) -> str:
    return template.replace("{code}", urllib.parse.quote(code, safe=""))


def official_url(carrier: CarrierCode, code: str) -> str | None:
    template = CATALOG[carrier].link_template
    return None if template is None else _fill(template, code)


def seventeen_track_url(code: str) -> str:
    return _fill(SEVENTEEN_TRACK_TEMPLATE, code)
