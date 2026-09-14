from datetime import UTC, datetime

import pytest

from vn_parcel_bot.carriers.models import TrackingEvent, TrackingResult
from vn_parcel_bot.carriers.modules.spx import spx_progress
from vn_parcel_bot.carriers.progress import stage_progress
from vn_parcel_bot.carriers.registry import current_snapshot
from vn_parcel_bot.services.formatting import progress_bar

T = datetime(2026, 9, 14, tzinfo=UTC)


def result_with(description, raw_status=None, location=None, **flags):
    event = TrackingEvent(time=T, description=description, location=location, raw_status=raw_status)
    return TrackingResult("spx", "SPXVN000000000001", True, (event,), **flags)


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Người bán đang chuẩn bị hàng", 10),
        ("Đơn vị vận chuyển lấy hàng thành công", 30),
        ("Đơn hàng đã đến kho 10-VPC Vinh Tuong Hub", 50),
        ("Hàng đã thông quan", 60),
        ("Đã đến bưu cục phát Vĩnh Tường", 80),
        ("Đang giao hàng", 95),
        ("Arrived at sorting center", 50),
        ("Out for delivery", 95),
        ("Something unrelated", None),
    ],
)
def test_stage_progress_keywords(description, expected):
    assert stage_progress(result_with(description)) == expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [("F000", 10), ("F100", 30), ("F440", 50), ("F510", 50), ("F599", 80), ("F600", 95)],
)
def test_spx_progress_uses_tracking_codes(code, expected):
    assert spx_progress(result_with("x", raw_status=code)) == expected


def test_spx_progress_falls_back_to_keywords():
    assert spx_progress(result_with("Đang giao hàng")) == 95


def test_snapshot_progress_handles_delivered_returned_and_missing():
    snapshot = current_snapshot()
    delivered = result_with("Giao hàng thành công", raw_status="F980", delivered=True)
    assert snapshot.progress("spx", delivered) == 100
    assert snapshot.progress("spx", result_with("Hoàn hàng", returned=True)) is None
    assert snapshot.progress("spx", TrackingResult("spx", "X", False)) is None
    assert snapshot.progress("gone", result_with("Đang giao hàng")) is None
    assert snapshot.progress("cainiao", result_with("Out for delivery")) == 95


def test_progress_bar():
    assert progress_bar(0) == "🟥" * 10
    assert progress_bar(80) == "🟩" * 8 + "🟥" * 2
    assert progress_bar(95) == "🟩" * 9 + "🟥"
    assert progress_bar(100) == "🟩" * 10
