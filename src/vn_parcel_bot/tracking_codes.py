import re

from vn_parcel_bot.carriers.registry import current_snapshot

_LAZADA_ORDER_PREFIX = re.compile(r"^\d{15}_(?=[0-9A-Z]{8,30}$)", re.ASCII)
_ORDER_NUMBER = re.compile(r"\d{15}", re.ASCII)
_SELLER_FLEET = re.compile(r"84\d{12}", re.ASCII)
_CODE_LIKE = re.compile(r"[0-9A-Z]{8,40}", re.ASCII)
_CODE_LIKE_MIN_DIGITS = 6
_TOKEN = re.compile(r"[0-9A-Za-z][0-9A-Za-z._\-]*[0-9A-Za-z]")
_SEPARATORS = re.compile(r"[\s\-]")
_STRIP_CHARS = ",;:()[]<>\"'."
_LAST4 = re.compile(r"\d{4}", re.ASCII)


def normalize_code(raw: str) -> str:
    code = _SEPARATORS.sub("", raw.upper()).strip(_STRIP_CHARS)
    return _LAZADA_ORDER_PREFIX.sub("", code)


def detect_carriers(code: str) -> list[str]:
    return list(current_snapshot().detect(code).candidates)


def is_order_number(code: str) -> bool:
    return _ORDER_NUMBER.fullmatch(code) is not None


def is_seller_fleet(code: str) -> bool:
    return _SELLER_FLEET.fullmatch(code) is not None


def is_code_like(code: str) -> bool:
    if _CODE_LIKE.fullmatch(code) is None:
        return False
    return sum(char.isdigit() for char in code) >= _CODE_LIKE_MIN_DIGITS


def extract_codes(text: str) -> list[str]:
    snapshot = current_snapshot()
    whole = normalize_code(text)
    known: list[str] = []
    fallback: list[str] = []
    for match in _TOKEN.finditer(text):
        code = normalize_code(match.group())
        detection = snapshot.detect(code)
        if (detection.candidates and not (detection.standalone_only and code != whole)) or (
            not detection.candidates and (is_order_number(code) or is_seller_fleet(code))
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
