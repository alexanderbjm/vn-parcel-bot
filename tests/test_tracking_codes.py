import pytest

from vn_parcel_bot.tracking_codes import (
    GENERIC_CODE_RE,
    detect_carriers,
    extract_codes,
    is_valid_last4,
    mask_code,
    normalize_code,
)


def test_normalize_strips_spaces_dashes_case():
    assert normalize_code(" spxvn 0533-8454 932c ") == "SPXVN05338454932C"


def test_normalize_strips_surrounding_punctuation():
    assert normalize_code("(841000072647),") == "841000072647"


def test_normalize_keeps_internal_dots():
    assert normalize_code("s1234567.mb12.d5.123456789.") == "S1234567.MB12.D5.123456789"


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("SPXVN05338454932C", ["spx"]),
        ("SPEVN000000000001", ["ninjavan"]),
        ("LP00123456789012", ["cainiao"]),
        ("LX123456789CN", ["cainiao"]),
        ("4PX3000123456789CN", ["fourpx"]),
        ("YT1234567890123456", ["yunexpress"]),
        ("EB123456789VN", ["vnpost"]),
        ("LEXVN00123456", ["lex"]),
        ("S1234567.MB12.D5.123456789", ["ghtk"]),
        ("841000072647", ["jt", "best", "viettelpost"]),
        ("8410000726470", ["best"]),
        ("GAN6DKKU12", ["ghn", "ninjavan"]),
    ],
)
def test_detect_each_rule(code, expected):
    assert detect_carriers(code) == expected


def test_detect_first_rule_wins():
    assert detect_carriers("SPXVN05338454932C") == ["spx"]
    assert detect_carriers("EB123456789VN") == ["vnpost"]


@pytest.mark.parametrize(
    "code", ["", "AB12", "ABCDEFGH", "12345678", "71426082060", "GAN6DKKU12345678"]
)
def test_detect_no_match(code):
    assert detect_carriers(code) == []


def test_generic_code_re():
    assert not GENERIC_CODE_RE.match("AB12C")
    assert GENERIC_CODE_RE.match("AB1234")
    assert not GENERIC_CODE_RE.match("A.B")


def test_extract_codes_mixed_text_in_order():
    text = "Mã: spxvn05338454932c và J&T 841000072647."
    assert extract_codes(text) == ["SPXVN05338454932C", "841000072647"]


def test_extract_codes_dedupes():
    assert extract_codes("841000072647 và 841000072647") == ["841000072647"]


def test_extract_codes_ignores_longer_digit_runs():
    assert extract_codes("84100007264701") == []


def test_extract_codes_generic_only_when_alone():
    assert extract_codes("GAN6DKKU12") == ["GAN6DKKU12"]
    assert extract_codes(" gan6dkku12 ") == ["GAN6DKKU12"]
    assert extract_codes("đơn GAN6DKKU12 nhé") == []
    assert extract_codes("IPHONE15PROMAX 841000072647") == ["841000072647"]


def test_extract_codes_dashed_code_in_text():
    assert extract_codes("mã SPXVN-0533-8454-932C nhé") == ["SPXVN05338454932C"]


def test_extract_codes_none():
    assert extract_codes("xin chào") == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1234", True), ("123", False), ("12345", False), ("12a4", False), (" 1234", False)],
)
def test_is_valid_last4(value, expected):
    assert is_valid_last4(value) is expected


def test_mask_code():
    assert mask_code("SPXVN05338454932C") == "SPXVN…32C"
