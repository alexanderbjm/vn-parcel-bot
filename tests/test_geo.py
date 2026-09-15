import pytest

from vn_parcel_bot import texts
from vn_parcel_bot.services.geo import PlaceParts, clean_place, format_distance, haversine_km
from vn_parcel_bot.services.geo_provinces import PROVINCES


@pytest.mark.parametrize(
    ("raw", "code", "district"),
    [
        ("21-HNI Thanh Tri 2 Hub", "HNI", "Thanh Tri"),
        ("24-HPG Hai An 3 Hub", "HPG", "Hai An"),
        ("BN B Mega SOC", "BN", None),
        ("11-TQG Son Duong Hub", "TQG", "Son Duong"),
        ("Bưu cục Quận 7", None, "Quận 7"),
        ("  Kho   HCM  ", None, "Kho HCM"),
    ],
)
def test_clean_place(raw, code, district):
    assert clean_place(raw) == PlaceParts(code, district)


def test_place_key_and_display():
    assert clean_place("21-HNI Thanh Tri 2 Hub").key == "HNI|Thanh Tri"
    assert clean_place("21-HNI Thanh Tri 2 Hub").display == "Kho Thanh Tri"
    assert clean_place("BN B Mega SOC").display == f"Kho {PROVINCES['BN'][0]}"
    assert clean_place("Bưu cục Quận 7").display == "Quận 7"
    assert clean_place("   ") == PlaceParts(None, None)


def test_haversine_and_distance_text():
    hanoi, haiphong = (21.03, 105.85), (20.86, 106.68)
    assert 85 < haversine_km(hanoi, haiphong) < 95
    assert haversine_km(hanoi, hanoi) == 0
    assert format_distance(0.4) == texts.DISTANCE_UNDER_1KM
    assert format_distance(4.54) == "~4.5 km"
    assert format_distance(12.4) == "~12 km"


def test_province_table_is_inside_vietnam():
    for required in ("HNI", "HCM", "HPG", "BN", "TQG", "VPC", "DNG"):
        assert required in PROVINCES
    for name, lat, lon in PROVINCES.values():
        assert name
        assert 8.0 <= lat <= 23.5
        assert 102.0 <= lon <= 110.0
