import hashlib
from dataclasses import replace
from datetime import datetime

import httpx

from vn_parcel_bot.carriers.api import PRIORITY_GENERIC, CarrierModule, Rule
from vn_parcel_bot.carriers.common import VN_TZ, clean_text, json_body, request
from vn_parcel_bot.carriers.models import CarrierCode, CarrierError, TrackingEvent, TrackingResult

GHN_TRACKING_URL = "https://fe-online-gateway.ghn.vn/order-tracking/public-api/client/tracking-logs"

GHN_STATUS_TEXT: dict[str, str] = {
    "draft": "Đơn nháp",
    "cancel": "Đã hủy",
    "ready_to_pick": "Chờ lấy hàng",
    "picking": "Đang lấy hàng",
    "money_collect_picking": "Đang thu tiền người gửi",
    "picked": "Đã lấy hàng",
    "storing": "Lưu kho",
    "transporting": "Đang luân chuyển hàng",
    "sorting": "Đang phân loại hàng",
    "delivering": "Đang giao hàng",
    "money_collect_delivering": "Đang thu tiền người nhận",
    "delivery_fail": "Giao hàng thất bại",
    "delivered": "Giao hàng thành công",
    "waiting_to_return": "Chờ trả hàng",
    "return": "Trả hàng",
    "return_transporting": "Đang luân chuyển hàng trả",
    "return_sorting": "Đang phân loại hàng trả",
    "returning": "Đang trả hàng",
    "return_fail": "Trả hàng thất bại",
    "returned": "Trả hàng thành công",
    "exception": "Đơn ngoại lệ",
    "lost": "Hàng thất lạc",
    "damage": "Hàng hư hỏng",
}


def ghn_phone_verify(code: str, last4: str) -> str:
    return hashlib.sha256(f"{code}|{last4}".encode()).hexdigest()


def _parse_error(detail: str) -> CarrierError:
    return CarrierError("ghn", "parse", detail)


def _action_time(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise _parse_error("log without action_at")
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise _parse_error("unparseable action_at") from exc
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=VN_TZ)


def _event(log: object) -> TrackingEvent:
    if not isinstance(log, dict):
        raise _parse_error("log is not an object")
    status = log["status"] if isinstance(log.get("status"), str) else ""
    time = _action_time(log.get("action_at"))
    description = clean_text(log.get("status_name") or "") or GHN_STATUS_TEXT.get(status) or status
    if not description:
        raise _parse_error("log without status")
    location = log.get("location")
    address = location.get("address") if isinstance(location, dict) else None
    return TrackingEvent(
        time=time,
        description=description,
        location=(clean_text(address) or None) if isinstance(address, str) else None,
        raw_status=status or None,
    )


def parse_ghn_response(payload: object, tracking_number: str) -> TrackingResult:
    if not isinstance(payload, dict):
        raise _parse_error("unexpected payload")
    not_found = TrackingResult(carrier="ghn", tracking_number=tracking_number, found=False)
    code = payload.get("code")
    if code == 400:
        return not_found
    if code != 200:
        raise CarrierError("ghn", "http_status", f"code={code}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise _parse_error("missing data")
    logs = data.get("tracking_logs")
    if logs is None or logs == []:
        return not_found
    if not isinstance(logs, list):
        raise _parse_error("tracking_logs is not a list")

    result = TrackingResult(
        carrier="ghn",
        tracking_number=tracking_number,
        found=True,
        events=tuple(_event(log) for log in logs),
    )
    order_info = data.get("order_info")
    order_status = order_info.get("status") if isinstance(order_info, dict) else None
    latest_status = result.latest.raw_status
    delivered = "delivered" in (order_status, latest_status)
    returned = not delivered and "returned" in (order_status, latest_status)
    return replace(result, delivered=delivered, returned=returned)


class GhnCarrier:
    code: CarrierCode = "ghn"
    display_name = "GHN"
    needs_phone = True

    async def fetch(
        self, http: httpx.AsyncClient, tracking_number: str, phone_last4: str | None = None
    ) -> TrackingResult:
        if phone_last4 is None:
            raise ValueError("GHN requires phone_last4")
        response = await request(
            http,
            "ghn",
            "POST",
            GHN_TRACKING_URL,
            json={
                "order_code": tracking_number,
                "phone_verify": ghn_phone_verify(tracking_number, phone_last4),
            },
            not_found_statuses=(400,),
        )
        if response.status_code == 400:
            try:
                payload = response.json()
            except ValueError:
                raise CarrierError("ghn", "http_status", "400") from None
            if not isinstance(payload, dict):
                raise CarrierError("ghn", "http_status", "400")
            return parse_ghn_response(payload, tracking_number)
        return parse_ghn_response(json_body("ghn", response), tracking_number)


MODULE = CarrierModule(
    code="ghn",
    display_name="GHN",
    order=60,
    needs_phone=True,
    rules=(
        Rule(
            r"(?=[0-9A-Z]*[A-Z])(?=[0-9A-Z]*\d)[0-9A-Z]{8,14}",
            PRIORITY_GENERIC,
            rank=0,
            standalone_only=True,
        ),
    ),
    examples=(("GAN6DKKU12", True), ("SPXVN05338454932C", False)),
    build_client=GhnCarrier,
)
