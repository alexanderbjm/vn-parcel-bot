import pytest

from vn_parcel_bot.tracking_codes import (
    detect_carriers,
    extract_codes,
    is_code_like,
    is_order_number,
    is_seller_fleet,
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


def test_normalize_drops_lazada_order_number_prefix():
    assert normalize_code("500000000000001_YT0000000000001") == "YT0000000000001"
    assert normalize_code(" 500000000000001_yt0000000000001 ") == "YT0000000000001"
    assert normalize_code("ABC_DEF") == "ABC_DEF"


def test_extract_codes_splits_lazada_cainiao_code_in_text():
    text = "Cainiao: Giao tiêu chuẩn 500000000000001_YT0000000000001"
    assert extract_codes(text) == ["YT0000000000001"]


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("SPXVN05338454932C", ["spx"]),
        ("SPEVN000000000001", ["ninjavan"]),
        ("LP00123456789012", ["cainiao"]),
        ("LX123456789CN", ["cainiao"]),
        ("4PX3000123456789CN", ["fourpx"]),
        ("YT1234567890123456", ["yunexpress"]),
        ("YT0000000000001", ["cainiao"]),
        ("SF0000000000001", ["sf"]),
        ("SF123456789012", ["sf"]),
        ("SF123456789012345", ["sf"]),
        ("LP0012345678901234", ["cainiao"]),
        ("EB123456789VN", ["vnpost"]),
        ("EMS1234567890", ["vnpost"]),
        ("LEXVN00123456", ["lex"]),
        ("S1234567.MB12.D5.123456789", ["ghtk"]),
        ("GHTK0012345678", ["ghtk"]),
        ("JNTXB0000000001", ["jt"]),
        ("JNTX0000000001", ["jt"]),
        ("JTE1000000001", ["jt"]),
        ("JNTVN000000001", ["jt"]),
        ("BESTMP0000000001VNA", ["best"]),
        ("BEST0000000001VN", ["best"]),
        ("BEST0000000001", ["best"]),
        ("841000072647", ["jt", "best", "viettelpost"]),
        ("8410000726470", ["best"]),
        ("773440000000001", ["cainiao"]),
        ("VTP0000000001", ["viettelpost"]),
        ("NLVN000000000001", ["ninjavan"]),
        ("YT123456789012345678", ["yunexpress"]),
        ("GAN6DKKU12", ["ghn", "ninjavan"]),
    ],
)
def test_detect_each_rule(code, expected):
    assert detect_carriers(code) == expected


def test_extract_codes_finds_jt_cross_border_code_in_text():
    assert extract_codes("J&T VN: Giao tiêu chuẩn JNTXB0000000001") == ["JNTXB0000000001"]


def test_extract_codes_finds_new_carrier_formats():
    text = (
        "Đơn SF123456789012345, Viettel Post VTP0000000001, "
        "GHTK GHTK0012345678 và Ninja NLVN000000000001."
    )
    assert extract_codes(text) == [
        "SF123456789012345",
        "VTP0000000001",
        "GHTK0012345678",
        "NLVN000000000001",
    ]


def test_detect_first_rule_wins():
    assert detect_carriers("SPXVN05338454932C") == ["spx"]
    assert detect_carriers("EB123456789VN") == ["vnpost"]


@pytest.mark.parametrize(
    "code",
    [
        "",
        "AB12",
        "ABCDEFGH",
        "12345678",
        "71426082060",
        "GAN6DKKU12345678",
        "84000000000001",
        "94000000000001",
    ],
)
def test_detect_no_match(code):
    assert detect_carriers(code) == []


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("500000000000001", True),
        ("50000000000000", False),
        ("5000000000000010", False),
        ("SPXVN05338454932C", False),
    ],
)
def test_is_order_number(code, expected):
    assert is_order_number(code) is expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("84000000000001", True),
        ("94000000000001", False),
        ("840000000001", False),
        ("840000000000011", False),
        ("84ABC000000001", False),
    ],
)
def test_is_seller_fleet(code, expected):
    assert is_seller_fleet(code) is expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("ABC1234567890DEF", True),
        ("71426082060", True),
        ("BESTMP0000000001VNA", True),
        ("IPHONE15PROMAX", False),
        ("ABCDEFGHIJ", False),
        ("1234567", False),
        ("1.250.000", False),
        ("A" * 41 + "123456", False),
    ],
)
def test_is_code_like(code, expected):
    assert is_code_like(code) is expected


def test_extract_codes_mixed_text_in_order():
    text = "Mã: spxvn05338454932c và J&T 841000072647."
    assert extract_codes(text) == ["SPXVN05338454932C", "841000072647"]


def test_extract_codes_dedupes():
    assert extract_codes("841000072647 và 841000072647") == ["841000072647"]


def test_extract_codes_does_not_pick_digit_substrings():
    assert extract_codes("9410000726470155") == ["9410000726470155"]


def test_extract_codes_generic_only_when_alone():
    assert extract_codes("GAN6DKKU12") == ["GAN6DKKU12"]
    assert extract_codes(" gan6dkku12 ") == ["GAN6DKKU12"]
    assert extract_codes("đơn GAN6DKKU12 nhé") == []
    assert extract_codes("IPHONE15PROMAX 841000072647") == ["841000072647"]


def test_extract_codes_dashed_code_in_text():
    assert extract_codes("mã SPXVN-0533-8454-932C nhé") == ["SPXVN05338454932C"]


def test_extract_codes_real_mixed_message():
    text = (
        "track 500000000000001 /track BESTMP0000000001VNA bestvn "
        "/track 84000000000001 /track 500000000000002"
    )
    assert extract_codes(text) == [
        "500000000000001",
        "BESTMP0000000001VNA",
        "84000000000001",
        "500000000000002",
    ]


def test_extract_codes_seller_fleet_counts_as_known():
    assert extract_codes("SPXVN05338454932C và 84000000000001") == [
        "SPXVN05338454932C",
        "84000000000001",
    ]


def test_extract_codes_code_like_fallback_only_without_known_codes():
    assert extract_codes("mã ABC1234567890DEF nhé") == ["ABC1234567890DEF"]
    assert extract_codes("SPXVN05338454932C gọi 0901234567") == ["SPXVN05338454932C"]


def test_extract_codes_none():
    assert extract_codes("xin chào") == []
    assert extract_codes("giá 1.250.000đ") == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1234", True), ("123", False), ("12345", False), ("12a4", False), (" 1234", False)],
)
def test_is_valid_last4(value, expected):
    assert is_valid_last4(value) is expected


def test_mask_code():
    assert mask_code("SPXVN05338454932C") == "SPXVN…32C"
