from vn_parcel_bot.carrier_catalog import CATALOG, TRACKED
from vn_parcel_bot.carriers import CARRIERS, get_carrier


def test_registry_keys_equal_tracked_in_order():
    assert tuple(CARRIERS) == TRACKED


def test_registry_attributes_match_catalog():
    for code, carrier in CARRIERS.items():
        assert carrier.code == code
        assert carrier.needs_phone == CATALOG[code].needs_phone
        assert carrier.display_name == CATALOG[code].display_name


def test_get_carrier():
    assert get_carrier("ghn") is CARRIERS["ghn"]
