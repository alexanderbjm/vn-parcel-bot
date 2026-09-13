import hashlib
import time
from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import UTC, datetime

import httpx

from vn_parcel_bot.carrier_catalog import CarrierCode
from vn_parcel_bot.carriers.common import clean_text, json_body, request
from vn_parcel_bot.carriers.models import CarrierError, TrackingEvent, TrackingResult

SPX_TRACKING_URL = "https://spx.vn/api/v2/fleet_order/tracking/search"
SPX_SIGNING_SECRET: str | None = None
DELIVERED_MARKERS = ("delivered", "giao hàng thành công", "giao thành công")
RETURNED_MARKERS = ("returned", "hoàn hàng thành công", "đã hoàn hàng", "trả hàng thành công")


def sign_spx_code(code: str, timestamp: int, secret: str) -> str:
    digest = hashlib.sha256(f"{code}{timestamp}{secret}".encode()).hexdigest()
    return f"{code}|{timestamp}{digest}"


def _parse_error(detail: str) -> CarrierError:
    return CarrierError("spx", "parse", detail)


def _has_marker(texts: Iterable[str], markers: tuple[str, ...]) -> bool:
    return any(marker in text.casefold() for text in texts for marker in markers)


def parse_spx_response(payload: object, tracking_number: str) -> TrackingResult:
    if not isinstance(payload, dict) or "retcode" not in payload:
        raise _parse_error("unexpected payload")
    retcode = payload["retcode"]
    if retcode != 0:
        raise _parse_error(f"retcode={retcode}")
    not_found = TrackingResult(carrier="spx", tracking_number=tracking_number, found=False)
    data = payload.get("data")
    if not isinstance(data, dict) or not data:
        return not_found
    items = data.get("tracking_list")
    if items is None or items == []:
        return not_found
    if not isinstance(items, list):
        raise _parse_error("tracking_list is not a list")

    events = []
    for item in items:
        if not isinstance(item, dict):
            raise _parse_error("tracking item is not an object")
        timestamp, message = item.get("timestamp"), item.get("message")
        if isinstance(timestamp, bool) or not isinstance(timestamp, int):
            raise _parse_error("tracking item without timestamp")
        if not isinstance(message, str):
            raise _parse_error("tracking item without message")
        description = clean_text(message.replace("\\n", " "))
        if not description:
            raise _parse_error("tracking item with empty message")
        code = item.get("code")
        events.append(
            TrackingEvent(
                time=datetime.fromtimestamp(timestamp, UTC),
                description=description,
                raw_status=None if code is None else str(code),
            )
        )

    result = TrackingResult(
        carrier="spx", tracking_number=tracking_number, found=True, events=tuple(events)
    )
    status_texts = [clean_text(data.get("current_status") or ""), result.latest.description]
    delivered = _has_marker(status_texts, DELIVERED_MARKERS)
    returned = not delivered and _has_marker(status_texts, RETURNED_MARKERS)
    return replace(result, delivered=delivered, returned=returned)


class SpxCarrier:
    code: CarrierCode = "spx"
    display_name = "SPX"
    needs_phone = False

    def __init__(
        self,
        *,
        secret: str | None = SPX_SIGNING_SECRET,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._secret = secret
        self._clock = clock

    async def fetch(
        self, http: httpx.AsyncClient, tracking_number: str, phone_last4: str | None = None
    ) -> TrackingResult:
        value = tracking_number
        if self._secret is not None:
            value = sign_spx_code(tracking_number, int(self._clock()), self._secret)
        response = await request(
            http, "spx", "GET", SPX_TRACKING_URL, params={"sls_tracking_number": value}
        )
        return parse_spx_response(json_body("spx", response), tracking_number)
