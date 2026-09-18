from dataclasses import replace
from datetime import UTC, datetime

import httpx

from vn_parcel_bot.carriers.api import PRIORITY_GENERIC, PRIORITY_PREFIXED, CarrierModule, Rule
from vn_parcel_bot.carriers.common import VN_TZ, clean_text, json_body, request
from vn_parcel_bot.carriers.models import CarrierCode, CarrierError, TrackingEvent, TrackingResult

NINJAVAN_TRACKING_URL = "https://api.ninjavan.co/vn/dash/1.2/public/orders"
NOT_FOUND_ERROR_CODE = 150002
DELIVERED_TYPES = ("DELIVERY_SUCCESS", "FORCED_SUCCESS", "FROM_DP_TO_CUSTOMER")
RETURNED_GRANULAR_STATUS = "returned to sender"

NINJAVAN_EVENT_TEXT: dict[str, str] = {
    "ADDED_TO_SHIPMENT": "Đã thêm vào chuyến hàng",
    "ARRIVED_AT_ORIGIN_HUB": "Đã đến kho gửi",
    "ARRIVED_AT_TRANSIT_HUB": "Đã đến kho trung chuyển",
    "ARRIVED_AT_DESTINATION_HUB": "Đã đến kho giao",
    "HUB_INBOUND_SCAN": "Đã nhập kho",
    "FIRST_HUB_INBOUND_SCAN": "Đã nhập kho đầu tiên",
    "PARCEL_ROUTING_SCAN": "Đang phân tuyến",
    "ROUTE_INBOUND_SCAN": "Đã nhận vào tuyến giao",
    "DRIVER_PICKUP_SCAN": "Tài xế đã lấy hàng",
    "DRIVER_INBOUND_SCAN": "Tài xế đang đi giao hàng",
    "DELIVERY_FAILURE": "Giao hàng thất bại",
    "DELIVERY_SUCCESS": "Giao hàng thành công",
    "FORCED_SUCCESS": "Giao hàng thành công",
    "FROM_SHIPPER_TO_DP": "Người gửi đã gửi hàng tại điểm nhận",
    "FROM_DRIVER_TO_DP": "Hàng đã đến điểm nhận",
    "FROM_DP_TO_DRIVER": "Điểm nhận đã giao hàng cho tài xế",
    "FROM_DP_TO_CUSTOMER": "Đã nhận hàng tại điểm nhận",
    "CANCEL": "Đơn đã bị hủy",
    "RESCHEDULE": "Đã hẹn lại lịch giao",
    "RESUME": "Tiếp tục xử lý đơn",
    "RTS": "Đang hoàn hàng về người gửi",
}


def _parse_error(detail: str) -> CarrierError:
    return CarrierError("ninjavan", "parse", detail)


def _get(mapping: object, snake: str, camel: str) -> object:
    if not isinstance(mapping, dict):
        return None
    return mapping[snake] if snake in mapping else mapping.get(camel)


def _event_time(value: object) -> datetime:
    if isinstance(value, int) and not isinstance(value, bool):
        return datetime.fromtimestamp(value / 1000, UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip())
        except ValueError as exc:
            raise _parse_error("unparseable event time") from exc
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=VN_TZ)
    raise _parse_error("event without time")


def _describe(event_type: str, data: dict) -> str:
    text = NINJAVAN_EVENT_TEXT.get(event_type) or event_type.replace("_", " ").capitalize()
    if event_type == "DELIVERY_FAILURE":
        reason = _get(data, "failure_reason", "failureReason")
        if isinstance(reason, dict):
            detail = clean_text(reason.get("vi") or reason.get("en") or "")
            if detail:
                text = f"{text} – {detail}"
    return text


def parse_ninjavan_response(payload: object, tracking_number: str) -> TrackingResult:
    if not isinstance(payload, dict):
        raise _parse_error("unexpected payload")
    if "events" not in payload and isinstance(payload.get("data"), dict):
        payload = payload["data"]
    raw_events = payload.get("events")
    if not isinstance(raw_events, list):
        raise _parse_error("missing events")
    if not raw_events:
        return TrackingResult(carrier="ninjavan", tracking_number=tracking_number, found=False)

    events = []
    for item in raw_events:
        if not isinstance(item, dict) or not isinstance(item.get("type"), str) or not item["type"]:
            raise _parse_error("event without type")
        data = item["data"] if isinstance(item.get("data"), dict) else {}
        hub = _get(data, "hub_name", "hubName")
        events.append(
            TrackingEvent(
                time=_event_time(item.get("time")),
                description=_describe(item["type"], data),
                location=(clean_text(hub) or None) if isinstance(hub, str) else None,
                raw_status=item["type"],
            )
        )

    result = TrackingResult(
        carrier="ninjavan", tracking_number=tracking_number, found=True, events=tuple(events)
    )
    granular = _get(payload, "granular_status", "granularStatus")
    returned = isinstance(granular, str) and clean_text(granular).casefold() == (
        RETURNED_GRANULAR_STATUS
    )
    delivered = not returned and result.latest.raw_status in DELIVERED_TYPES
    return replace(result, delivered=delivered, returned=returned)


class NinjaVanCarrier:
    code: CarrierCode = "ninjavan"
    display_name = "🥷 Ninja Van"
    needs_phone = False

    async def fetch(
        self, http: httpx.AsyncClient, tracking_number: str, phone_last4: str | None = None
    ) -> TrackingResult:
        response = await request(
            http,
            "ninjavan",
            "GET",
            NINJAVAN_TRACKING_URL,
            params={"tracking_id": tracking_number},
            not_found_statuses=(404,),
        )
        if response.status_code == 404:
            try:
                payload = response.json()
            except ValueError:
                raise CarrierError("ninjavan", "http_status", "404") from None
            error = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(error, dict) and error.get("code") == NOT_FOUND_ERROR_CODE:
                return TrackingResult(
                    carrier="ninjavan", tracking_number=tracking_number, found=False
                )
            raise CarrierError("ninjavan", "http_status", "404")
        return parse_ninjavan_response(json_body("ninjavan", response), tracking_number)


MODULE = CarrierModule(
    code="ninjavan",
    display_name="🥷 Ninja Van",
    order=50,
    rules=(
        Rule(r"(SPEVN|NLVN|NVN)[0-9A-Z]{6,20}", PRIORITY_PREFIXED),
        Rule(
            r"(?=[0-9A-Z]*[A-Z])(?=[0-9A-Z]*\d)[0-9A-Z]{8,14}",
            PRIORITY_GENERIC,
            rank=1,
            standalone_only=True,
        ),
    ),
    examples=(
        ("SPEVN000000000001", True),
        ("NLVN000000000001", True),
        ("GAN6DKKU12", True),
    ),
    build_client=NinjaVanCarrier,
)
