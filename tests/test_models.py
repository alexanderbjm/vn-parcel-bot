from datetime import UTC, datetime, timedelta, timezone

import pytest

from vn_parcel_bot.carriers.models import CarrierError, TrackingEvent, TrackingResult

T = datetime(2026, 9, 1, 1, 0, tzinfo=UTC)


def test_event_requires_aware_time():
    with pytest.raises(ValueError):
        TrackingEvent(time=datetime(2026, 9, 1, 8, 0), description="x")


def test_event_key_stable_and_16_hex():
    a = TrackingEvent(time=T, description="Đang giao hàng", location="Kho HCM")
    b = TrackingEvent(time=T, description="Đang giao hàng", location="Kho HCM")
    assert a.key == b.key
    assert len(a.key) == 16
    int(a.key, 16)


def test_event_key_ignores_whitespace_and_case():
    a = TrackingEvent(time=T, description="Đang  giao hàng ")
    b = TrackingEvent(time=T, description="đang giao hàng")
    assert a.key == b.key


def test_event_key_same_instant_different_tz():
    local = datetime(2026, 9, 1, 8, 0, tzinfo=timezone(timedelta(hours=7)))
    assert (
        TrackingEvent(time=local, description="x").key == TrackingEvent(time=T, description="x").key
    )


def test_event_key_changes_with_description_or_location():
    base = TrackingEvent(time=T, description="x", location="a")
    assert base.key != TrackingEvent(time=T, description="y", location="a").key
    assert base.key != TrackingEvent(time=T, description="x", location="b").key


def test_event_key_ignores_microseconds():
    a = TrackingEvent(time=T.replace(microsecond=123456), description="x")
    assert a.key == TrackingEvent(time=T, description="x").key


def test_result_sorts_events_ascending_stably():
    t1a = TrackingEvent(time=T, description="a")
    t1b = TrackingEvent(time=T, description="b")
    t2 = TrackingEvent(time=T + timedelta(hours=1), description="c")
    result = TrackingResult(
        carrier="spx", tracking_number="SPXVN000000000001", found=True, events=(t2, t1a, t1b)
    )
    assert result.events == (t1a, t1b, t2)


def test_result_latest():
    t1 = TrackingEvent(time=T, description="a")
    t2 = TrackingEvent(time=T + timedelta(hours=1), description="b")
    assert TrackingResult("spx", "X", True, (t2, t1)).latest == t2
    assert TrackingResult("spx", "X", False).latest is None


def test_carrier_error_str_and_attrs():
    err = CarrierError("spx", "network", "timeout")
    assert str(err) == "spx:network: timeout"
    assert (err.carrier, err.reason, err.detail) == ("spx", "network", "timeout")


def test_event_identity_survives_a_reworded_translation():
    """The bug this guards: retranslating locations re-created every event and replayed a
    parcel's whole history as new."""
    said = "【东莞市】快件已到达|东莞市"
    first = TrackingEvent(time=T, description="Đã đến Đông Quản", location="东莞市", identity=said)
    later = TrackingEvent(
        time=T, description="Kiện hàng đã tới Đông Quản", location="Đông Quản", identity=said
    )
    assert first.key == later.key, "same scan, only rendered differently"


def test_event_identity_still_separates_different_scans():
    a = TrackingEvent(time=T, description="giống nhau", identity="已揽收|上海市")
    b = TrackingEvent(time=T, description="giống nhau", identity="已签收|上海市")
    assert a.key != b.key
