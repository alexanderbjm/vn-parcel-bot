from dataclasses import replace
from datetime import UTC, datetime

import httpx

from vn_parcel_bot.carrier_catalog import CarrierCode
from vn_parcel_bot.carriers.common import clean_text, json_body, request
from vn_parcel_bot.carriers.models import CarrierError, TrackingEvent, TrackingResult

SPX_ORDER_INFO_URL = "https://spx.vn/shipment/order/open/order/get_order_info"
NOT_FOUND_RETCODES = (2,)
PUBLIC_DISPLAY_FLAG = 1
DELIVERED_MILESTONE = 8
DELIVERED_TRACKING_CODES = ("F980",)
RETURNED_MARKERS = ("return", "hoàn hàng", "trả hàng")


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


class SpxCarrier:
    code: CarrierCode = "spx"
    display_name = "SPX"
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
