"""Stage-based delivery progress shared by carrier modules; a module can override it."""

from vn_parcel_bot.carriers.models import TrackingResult

STAGE_MARKERS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (95, ("đang giao", "out for delivery", "đang phát hàng", "shipper đang")),
    (80, ("bưu cục phát", "delivery hub", "delivery station", "arrived at delivery")),
    (
        60,
        (
            "thông quan",
            "customs clearance complete",
            "cleared customs",
            "import clearance",
            "arrived in vietnam",
            "đã đến việt nam",
        ),
    ),
    (
        50,
        (
            "kho",
            "hub",
            "trung tâm",
            "sorting",
            "phân loại",
            "đang vận chuyển",
            "in transit",
            "departed",
            "arrived",
        ),
    ),
    (
        30,
        (
            "lấy hàng thành công",
            "đã lấy hàng",
            "picked up",
            "nhận hàng thành công",
            "accepted by carrier",
        ),
    ),
    (
        10,
        ("chuẩn bị hàng", "tạo đơn", "chờ lấy", "order created", "info received", "label created"),
    ),
)


def stage_progress(result: TrackingResult) -> int | None:
    latest = result.latest
    if latest is None:
        return None
    text = f"{latest.description} {latest.location or ''}".casefold()
    for percent, markers in STAGE_MARKERS:
        if any(marker in text for marker in markers):
            return percent
    return None
