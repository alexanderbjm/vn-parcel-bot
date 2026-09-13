import pytest

from vn_parcel_bot.bot.parsing import parse_ref_and_text, parse_track_args, route_text


def test_track_args_none_when_empty():
    assert parse_track_args([]) is None


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["SPXVN000000000001"], ("SPXVN000000000001", None, None)),
        (["840000000001", "1234"], ("840000000001", "1234", None)),
        (["SPXVN", "0000", "0000", "0001"], ("SPXVN000000000001", None, None)),
        (["8400", "0000", "0001", "1234"], ("840000000001", "1234", None)),
        (["GA0000000001", "ghn"], ("GA0000000001", None, "ghn")),
        (["GA0000000001", "1234", "GHN"], ("GA0000000001", "1234", "ghn")),
        (["ABCD1234", "0001", "ninjavan"], ("ABCD12340001", None, "ninjavan")),
        (["ghn"], ("GHN", None, None)),
        (["spxvn000000000001", "J&T"], ("SPXVN000000000001", None, "jt")),
    ],
)
def test_track_args(args, expected):
    assert parse_track_args(args) == expected


def test_ref_and_text():
    assert parse_ref_and_text([]) is None
    assert parse_ref_and_text(["1"]) == ("1", None)
    assert parse_ref_and_text(["1", "Áo", "khoác"]) == ("1", "Áo khoác")


def test_route_phone_for_pending():
    route = route_text(" 1234 ", True)
    assert route.kind == "phone_for_pending"
    assert route.last4 == "1234"


def test_route_codes_override_pending():
    route = route_text("SPXVN000000000001", True)
    assert route.kind == "codes"
    assert route.codes == ("SPXVN000000000001",)


def test_route_invalid_phone_when_pending():
    assert route_text("12", True).kind == "invalid_phone"


def test_route_unknown():
    assert route_text("xin chào", False).kind == "unknown"
    assert route_text("1234", False).kind == "unknown"


def test_route_multiple_codes():
    route = route_text("Đơn SPXVN000000000001 và 841000072647", False)
    assert route.codes == ("SPXVN000000000001", "841000072647")


def test_route_generic_code_alone():
    assert route_text("GA0000000001", False).codes == ("GA0000000001",)
