from datetime import timedelta

from vn_parcel_bot.constants import (
    IN_TRANSIT_CHECK_INTERVAL,
    MAX_CHECK_GAP,
    NEAR_DELIVERY_CHECK_INTERVAL,
    NEAR_DELIVERY_PROGRESS,
)


def capped(interval: timedelta) -> timedelta:
    """Shorten any wait to the ceiling, so every order is checked at least that often."""
    return min(interval, MAX_CHECK_GAP)


def check_interval(state: str, progress: int | None, pending_interval: timedelta) -> timedelta:
    """Wait before a parcel's next check: the closer it is to arriving, the sooner.

    Parcels without data use POLL_INTERVAL_MINUTES, which also caps the shorter intervals,
    and nothing waits longer than MAX_CHECK_GAP.
    """
    if state != "in_transit":
        return capped(pending_interval)
    if progress is not None and progress >= NEAR_DELIVERY_PROGRESS:
        return capped(min(NEAR_DELIVERY_CHECK_INTERVAL, pending_interval))
    return capped(min(IN_TRANSIT_CHECK_INTERVAL, pending_interval))
