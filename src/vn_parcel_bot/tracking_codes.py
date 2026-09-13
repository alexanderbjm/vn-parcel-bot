import re

from vn_parcel_bot.carrier_catalog import CarrierCode

GENERIC_CODE_RE = re.compile(r"^[0-9A-Z][0-9A-Z.]{4,38}[0-9A-Z]$", re.ASCII)

_RULES: tuple[tuple[re.Pattern[str], tuple[CarrierCode, ...]], ...] = tuple(
    (re.compile(pattern, re.ASCII), candidates)
    for pattern, candidates in (
        (r"SPXVN[0-9A-Z]{8,16}", ("spx",)),
        (r"SPEVN[0-9A-Z]{6,20}", ("ninjavan",)),
        (r"LP\d{14}", ("cainiao",)),
        (r"[A-Z]{2}\d{9}CN", ("cainiao",)),
        (r"4PX[0-9A-Z]{10,20}", ("fourpx",)),
        (r"YT\d{16}", ("yunexpress",)),
        (r"[A-Z]{2}\d{9}VN", ("vnpost",)),
        (r"(LEXVN|LXVN|LVS)[0-9A-Z]{6,20}", ("lex",)),
        (r"S\d{5,10}(\.[0-9A-Z]{1,12}){1,4}", ("ghtk",)),
        (r"\d{12}", ("jt", "best", "viettelpost")),
        (r"\d{13}", ("best",)),
        (r"(?=[0-9A-Z]*[A-Z])(?=[0-9A-Z]*\d)[0-9A-Z]{8,14}", ("ghn", "ninjavan")),
    )
)
_GENERIC_ONLY_RULE_INDEX = 11
_TOKEN = re.compile(r"[0-9A-Za-z][0-9A-Za-z.\-]*[0-9A-Za-z]")
_SEPARATORS = re.compile(r"[\s\-]")
_STRIP_CHARS = ",;:()[]<>\"'."
_LAST4 = re.compile(r"\d{4}", re.ASCII)


def _rule_index(code: str) -> int | None:
    for index, (pattern, _) in enumerate(_RULES):
        if pattern.fullmatch(code):
            return index
    return None


def normalize_code(raw: str) -> str:
    return _SEPARATORS.sub("", raw.upper()).strip(_STRIP_CHARS)


def detect_carriers(code: str) -> list[CarrierCode]:
    index = _rule_index(code)
    return [] if index is None else list(_RULES[index][1])


def extract_codes(text: str) -> list[str]:
    whole = normalize_code(text)
    codes: list[str] = []
    for match in _TOKEN.finditer(text):
        code = normalize_code(match.group())
        index = _rule_index(code)
        if index is None or (index == _GENERIC_ONLY_RULE_INDEX and code != whole):
            continue
        if code not in codes:
            codes.append(code)
    return codes


def is_valid_last4(value: str) -> bool:
    return _LAST4.fullmatch(value) is not None


def mask_code(code: str) -> str:
    return f"{code[:5]}…{code[-3:]}"
