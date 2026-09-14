import re

from vn_parcel_bot.carrier_catalog import CarrierCode

_JT_CROSS_BORDER = r"JNTX[A-Z]?\d{8,12}"
_LAZADA_CAINIAO = r"YT\d{13}"

_RULES: tuple[tuple[re.Pattern[str], tuple[CarrierCode, ...], bool], ...] = tuple(
    (re.compile(pattern, re.ASCII), candidates, standalone_only)
    for pattern, candidates, standalone_only in (
        (r"SPXVN[0-9A-Z]{8,16}", ("spx",), False),
        (r"SPEVN[0-9A-Z]{6,20}", ("ninjavan",), False),
        (r"LP\d{14}", ("cainiao",), False),
        (r"[A-Z]{2}\d{9}CN", ("cainiao",), False),
        (r"4PX[0-9A-Z]{10,20}", ("fourpx",), False),
        (r"YT\d{16}", ("yunexpress",), False),
        (r"[A-Z]{2}\d{9}VN", ("vnpost",), False),
        (r"(LEXVN|LXVN|LVS)[0-9A-Z]{6,20}", ("lex",), False),
        (r"S\d{5,10}(\.[0-9A-Z]{1,12}){1,4}", ("ghtk",), False),
        (_JT_CROSS_BORDER, ("jt",), False),
        (_LAZADA_CAINIAO, ("cainiao",), False),
        (r"SF\d{13}", ("sf",), False),
        (r"BEST[A-Z]{0,6}\d{8,16}VN[A-Z]{0,3}", ("best",), False),
        (r"\d{12}", ("jt", "best", "viettelpost"), False),
        (r"\d{13}", ("best",), False),
        (r"(?=[0-9A-Z]*[A-Z])(?=[0-9A-Z]*\d)[0-9A-Z]{8,14}", ("ghn", "ninjavan"), True),
    )
)
_JT_CROSS_BORDER_RE = re.compile(_JT_CROSS_BORDER, re.ASCII)
_LAZADA_CAINIAO_RE = re.compile(_LAZADA_CAINIAO, re.ASCII)
_LAZADA_ORDER_PREFIX = re.compile(r"^\d{15}_(?=[0-9A-Z]{8,30}$)", re.ASCII)
_ORDER_NUMBER = re.compile(r"\d{15}", re.ASCII)
_SELLER_FLEET = re.compile(r"84\d{12}", re.ASCII)
_CODE_LIKE = re.compile(r"[0-9A-Z]{8,40}", re.ASCII)
_CODE_LIKE_MIN_DIGITS = 6
_TOKEN = re.compile(r"[0-9A-Za-z][0-9A-Za-z._\-]*[0-9A-Za-z]")
_SEPARATORS = re.compile(r"[\s\-]")
_STRIP_CHARS = ",;:()[]<>\"'."
_LAST4 = re.compile(r"\d{4}", re.ASCII)


def _match(code: str) -> tuple[tuple[CarrierCode, ...], bool] | None:
    for pattern, candidates, standalone_only in _RULES:
        if pattern.fullmatch(code):
            return candidates, standalone_only
    return None


def normalize_code(raw: str) -> str:
    code = _SEPARATORS.sub("", raw.upper()).strip(_STRIP_CHARS)
    return _LAZADA_ORDER_PREFIX.sub("", code)


def detect_carriers(code: str) -> list[CarrierCode]:
    rule = _match(code)
    return [] if rule is None else list(rule[0])


def is_jt_cross_border(code: str) -> bool:
    return _JT_CROSS_BORDER_RE.fullmatch(code) is not None


def is_lazada_cainiao(code: str) -> bool:
    return _LAZADA_CAINIAO_RE.fullmatch(code) is not None


def is_order_number(code: str) -> bool:
    return _ORDER_NUMBER.fullmatch(code) is not None


def is_seller_fleet(code: str) -> bool:
    return _SELLER_FLEET.fullmatch(code) is not None


def is_code_like(code: str) -> bool:
    if _CODE_LIKE.fullmatch(code) is None:
        return False
    return sum(char.isdigit() for char in code) >= _CODE_LIKE_MIN_DIGITS


def extract_codes(text: str) -> list[str]:
    whole = normalize_code(text)
    known: list[str] = []
    fallback: list[str] = []
    for match in _TOKEN.finditer(text):
        code = normalize_code(match.group())
        rule = _match(code)
        if (rule is not None and not (rule[1] and code != whole)) or (
            rule is None and (is_order_number(code) or is_seller_fleet(code))
        ):
            target = known
        elif is_code_like(code):
            target = fallback
        else:
            continue
        if code not in target:
            target.append(code)
    return known or fallback


def is_valid_last4(value: str) -> bool:
    return _LAST4.fullmatch(value) is not None


def mask_code(code: str) -> str:
    return f"{code[:5]}…{code[-3:]}"
