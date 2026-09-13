from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import httpx

from vn_parcel_bot.carrier_catalog import CarrierCode
from vn_parcel_bot.carriers.common import clean_text, json_body, parse_gmt_offset, request
from vn_parcel_bot.carriers.models import CarrierError, TrackingEvent, TrackingResult

CAINIAO_TRACKING_URL = "https://global.cainiao.com/global/detail.json"
DELIVERED_ACTION_CODES = ("GTMS_SIGNED",)
_DEFAULT_TZ = timezone(timedelta(hours=8))


def _parse_error(detail: str) -> CarrierError:
    return CarrierError("cainiao", "parse", detail)


def _event_time(item: dict) -> datetime:
    millis = item.get("time")
    if isinstance(millis, int) and not isinstance(millis, bool):
        return datetime.fromtimestamp(millis / 1000, UTC)
    text = item.get("timeStr")
    if isinstance(text, str):
        try:
            naive = datetime.strptime(text.strip(), "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise _parse_error("unparseable timeStr") from exc
        return naive.replace(tzinfo=parse_gmt_offset(item.get("timeZone"), _DEFAULT_TZ))
    raise _parse_error("event without time")


def parse_cainiao_response(payload: object, tracking_number: str) -> TrackingResult:
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise _parse_error("unsuccessful response")
    module = payload.get("module")
    if not isinstance(module, list) or not module or not isinstance(module[0], dict):
        raise _parse_error("missing module")
    details = module[0].get("detailList")
    if details is None or details == []:
        return TrackingResult(carrier="cainiao", tracking_number=tracking_number, found=False)
    if not isinstance(details, list):
        raise _parse_error("detailList is not a list")

    events = []
    for item in details:
        if not isinstance(item, dict):
            raise _parse_error("event is not an object")
        description = clean_text(item.get("desc") or "") or clean_text(
            item.get("standerdDesc") or ""
        )
        if not description:
            raise _parse_error("event without description")
        action = item.get("actionCode")
        events.append(
            TrackingEvent(
                time=_event_time(item),
                description=description,
                raw_status=str(action) if action else None,
            )
        )

    result = TrackingResult(
        carrier="cainiao", tracking_number=tracking_number, found=True, events=tuple(events)
    )
    latest_code = result.latest.raw_status or ""
    delivered = latest_code in DELIVERED_ACTION_CODES
    returned = not delivered and "RETURN" in latest_code.upper()
    return replace(result, delivered=delivered, returned=returned)


class CainiaoCarrier:
    code: CarrierCode = "cainiao"
    display_name = "Cainiao"
    needs_phone = False

    async def fetch(
        self, http: httpx.AsyncClient, tracking_number: str, phone_last4: str | None = None
    ) -> TrackingResult:
        response = await request(
            http,
            "cainiao",
            "GET",
            CAINIAO_TRACKING_URL,
            params={"mailNos": tracking_number, "lang": "en-US", "language": "en-US"},
        )
        return parse_cainiao_response(json_body("cainiao", response), tracking_number)
