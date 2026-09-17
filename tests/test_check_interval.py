from datetime import timedelta

import pytest

from vn_parcel_bot.constants import MAX_CHECK_GAP
from vn_parcel_bot.services.scheduling import capped, check_interval

TWENTY = timedelta(minutes=20)


@pytest.mark.parametrize(
    ("state", "progress", "minutes"),
    [
        ("pending", None, 20),
        ("in_transit", None, 10),
        ("in_transit", 50, 10),
        ("in_transit", 79, 10),
        ("in_transit", 80, 3),
        ("in_transit", 95, 3),
        ("delivered", 100, 20),
    ],
)
def test_check_interval_follows_the_delivery_stage(state, progress, minutes):
    assert check_interval(state, progress, TWENTY) == timedelta(minutes=minutes)


def test_poll_interval_caps_the_stage_intervals():
    five = timedelta(minutes=5)
    assert check_interval("in_transit", 50, five) == five
    assert check_interval("in_transit", 90, five) == timedelta(minutes=3)


def test_no_wait_is_ever_longer_than_the_ceiling():
    """However the interval is worked out, an order is never left unchecked for longer."""
    day = timedelta(days=1)
    assert MAX_CHECK_GAP.total_seconds() == 2 * 3600
    assert check_interval("pending", None, day) == MAX_CHECK_GAP
    assert check_interval("delivered", 100, day) == MAX_CHECK_GAP
    assert check_interval("in_transit", None, day) == timedelta(minutes=10)


def test_capped_leaves_shorter_waits_alone():
    assert capped(timedelta(days=1)) == MAX_CHECK_GAP
    assert capped(timedelta(minutes=3)) == timedelta(minutes=3)
    assert capped(MAX_CHECK_GAP) == MAX_CHECK_GAP
