import re
from dataclasses import replace
from datetime import UTC, datetime

import httpx

from vn_parcel_bot.carriers.api import PRIORITY_PREFIXED, CarrierModule, Rule
from vn_parcel_bot.carriers.common import clean_text, json_body, request
from vn_parcel_bot.carriers.models import CarrierCode, CarrierError, TrackingEvent, TrackingResult
from vn_parcel_bot.carriers.progress import stage_progress

SPX_ORDER_INFO_URL = "https://spx.vn/shipment/order/open/order/get_order_info"
NOT_FOUND_RETCODES = (2,)
PUBLIC_DISPLAY_FLAG = 1
DELIVERED_MILESTONE = 8
DELIVERED_TRACKING_CODES = ("F980",)
RETURNED_MARKERS = ("return", "hoàn hàng", "trả hàng")
SPX_TRACKING_CODE = re.compile(r"F(\d{3})", re.ASCII)
# "Đơn hàng đã đến kho 21-HNI Thanh Tri 2 Hub": the hub named in the status text.
SPX_HUB = re.compile(r"(?:đến|rời|tại)\s+kho\s+(\S.*)$", re.IGNORECASE)


def _parse_error(detail: str) -> CarrierError:
    return CarrierError("spx", "parse", detail)


def _location(record: dict, description: str) -> str | None:
    current = record.get("current_location")
    if not isinstance(current, dict):
        return None
    name = clean_text(current.get("location_name") or "")
    if not name or name.casefold() in description.casefold():
        return None
    return name


def _public_record(record: object) -> tuple[TrackingEvent, dict] | None:
    if not isinstance(record, dict):
        raise _parse_error("record is not an object")
    if record.get("display_flag") != PUBLIC_DISPLAY_FLAG:
        return None
    timestamp = record.get("actual_time")
    if isinstance(timestamp, bool) or not isinstance(timestamp, int):
        raise _parse_error("record without actual_time")
    description = clean_text(record.get("description") or "")
    if not description:
        raise _parse_error("record without description")
    code = record.get("tracking_code")
    event = TrackingEvent(
        time=datetime.fromtimestamp(timestamp, UTC),
        description=description,
        location=_location(record, description),
        raw_status=str(code) if code else None,
    )
    return event, record


def parse_spx_response(payload: object, tracking_number: str) -> TrackingResult:
    if not isinstance(payload, dict) or "retcode" not in payload:
        raise _parse_error("unexpected payload")
    not_found = TrackingResult(carrier="spx", tracking_number=tracking_number, found=False)
    retcode = payload["retcode"]
    if retcode in NOT_FOUND_RETCODES:
        return not_found
    if retcode != 0:
        raise _parse_error(f"retcode={retcode}")
    data = payload.get("data")
    if not isinstance(data, dict) or not data:
        return not_found
    info = data.get("sls_tracking_info")
    if info is None:
        return not_found
    if not isinstance(info, dict):
        raise _parse_error("sls_tracking_info is not an object")
    records = info.get("records")
    if records is None or records == []:
        return not_found
    if not isinstance(records, list):
        raise _parse_error("records is not a list")

    kept = [pair for record in records if (pair := _public_record(record)) is not None]
    if not kept:
        return not_found

    result = TrackingResult(
        carrier="spx",
        tracking_number=tracking_number,
        found=True,
        events=tuple(event for event, _ in kept),
    )
    _, latest = max(kept, key=lambda pair: pair[0].time)
    delivered = (
        latest.get("milestone_code") == DELIVERED_MILESTONE
        or latest.get("tracking_code") in DELIVERED_TRACKING_CODES
    )
    status_texts = [
        clean_text(latest.get(field) or "").casefold()
        for field in ("description", "tracking_name", "milestone_name")
    ]
    returned = not delivered and any(
        marker in text for text in status_texts for marker in RETURNED_MARKERS
    )
    return replace(result, delivered=delivered, returned=returned)


def spx_progress(result: TrackingResult) -> int | None:
    latest = result.latest
    match = SPX_TRACKING_CODE.fullmatch(latest.raw_status or "") if latest else None
    if match is None:
        return stage_progress(result)
    number = int(match.group(1))
    if number < 100:
        return 10
    if number < 400:
        return 30
    if number < 599:
        return 50
    if number < 600:
        return 80
    return 95


class SpxCarrier:
    code: CarrierCode = "spx"
    display_name = "🧡 SPX"
    needs_phone = False

    async def fetch(
        self, http: httpx.AsyncClient, tracking_number: str, phone_last4: str | None = None
    ) -> TrackingResult:
        response = await request(
            http,
            "spx",
            "GET",
            SPX_ORDER_INFO_URL,
            params={"language_code": "vi", "spx_tn": tracking_number},
        )
        return parse_spx_response(json_body("spx", response), tracking_number)


def spx_place(event: TrackingEvent) -> str | None:
    if event.location:
        return event.location
    match = SPX_HUB.search(event.description)
    return match.group(1).strip() if match else None


MODULE = CarrierModule(
    code="spx",
    display_name="🧡 SPX",
    order=10,
    rules=(Rule(r"SPXVN[0-9A-Z]{8,16}", PRIORITY_PREFIXED),),
    examples=(("SPXVN05338454932C", True), ("SPEVN000000000001", False)),
    # Every real SPX code stored so far (2026-09-15) has 17 characters.
    code_lengths=(17,),
    build_client=SpxCarrier,
    progress=spx_progress,
    place=spx_place,
)
