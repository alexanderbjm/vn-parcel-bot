from datetime import timedelta

from vn_parcel_bot.constants import (
    IN_TRANSIT_CHECK_INTERVAL,
    NEAR_DELIVERY_CHECK_INTERVAL,
    NEAR_DELIVERY_PROGRESS,
)


def check_interval(state: str, progress: int | None, pending_interval: timedelta) -> timedelta:
    """Wait before a parcel's next check: the closer it is to arriving, the sooner.

    Parcels without data use POLL_INTERVAL_MINUTES, which also caps the shorter intervals.
    """
    if state != "in_transit":
        return pending_interval
    if progress is not None and progress >= NEAR_DELIVERY_PROGRESS:
        return min(NEAR_DELIVERY_CHECK_INTERVAL, pending_interval)
    return min(IN_TRANSIT_CHECK_INTERVAL, pending_interval)
