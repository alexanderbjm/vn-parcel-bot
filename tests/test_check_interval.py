from datetime import timedelta

import pytest

from vn_parcel_bot.services.scheduling import check_interval

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
