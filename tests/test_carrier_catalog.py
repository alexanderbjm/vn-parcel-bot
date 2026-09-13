import pytest

from vn_parcel_bot.carrier_catalog import (
    CATALOG,
    TRACKED,
    is_tracked,
    needs_phone,
    official_url,
    parse_carrier_alias,
    seventeen_track_url,
)


def test_catalog_has_twelve_carriers_in_table_order():
    assert list(CATALOG) == [
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
    assert all(info.code == code for code, info in CATALOG.items())


def test_tracked_tuple():
    assert TRACKED == ("spx", "jt", "cainiao", "fourpx", "ninjavan", "ghn")
    assert tuple(code for code, info in CATALOG.items() if info.tracked) == TRACKED
    assert is_tracked("ghn") and not is_tracked("ghtk")


def test_needs_phone_only_jt_and_ghn():
    assert {code for code in CATALOG if needs_phone(code)} == {"jt", "ghn"}


def test_link_only_carriers_have_templates_tracked_have_none():
    for info in CATALOG.values():
        if info.tracked:
            assert info.link_template is None
        else:
            assert info.link_template and info.link_template.startswith("https://")


def test_display_names():
    assert CATALOG["jt"].display_name == "J&T"
    assert CATALOG["lex"].display_name == "LEX VN"
    assert CATALOG["fourpx"].display_name == "4PX"


def test_official_url_quotes_code():
    assert official_url("ghtk", "S123.AB") == "https://i.ghtk.vn/S123.AB"
    assert "YT1%232" in official_url("yunexpress", "YT1#2")


def test_official_url_without_placeholder():
    assert official_url("viettelpost", "123") == CATALOG["viettelpost"].link_template


def test_official_url_tracked_is_none():
    assert official_url("spx", "SPXVN05338454932C") is None


def test_seventeen_track_url():
    assert seventeen_track_url("EB123456789VN") == "https://t.17track.net/vi#nums=EB123456789VN"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("J&T", "jt"),
        ("jnt", "jt"),
        ("4PX", "fourpx"),
        ("Ninja-Van", "ninjavan"),
        ("EMS", "vnpost"),
        ("lazada", "lex"),
        ("Viettel Post", "viettelpost"),
        ("ghn", "ghn"),
        ("abc", None),
        ("", None),
    ],
)
def test_parse_carrier_alias_variants(text, expected):
    assert parse_carrier_alias(text) == expected
