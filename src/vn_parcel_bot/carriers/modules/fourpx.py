from dataclasses import replace
from datetime import datetime, timedelta, timezone

import httpx

from vn_parcel_bot.carriers.api import PRIORITY_PREFIXED, CarrierModule, Rule
from vn_parcel_bot.carriers.common import clean_text, json_body, parse_gmt_offset, request
from vn_parcel_bot.carriers.models import CarrierCode, CarrierError, TrackingEvent, TrackingResult

FOURPX_TRACKING_URL = "https://track.4px.com/track/v2/front/listTrackV3"
DELIVERED_CODE_PREFIX = "FPX_S_OK"
_DEFAULT_TZ = timezone(timedelta(hours=8))


def _parse_error(detail: str) -> CarrierError:
    return CarrierError("fourpx", "parse", detail)


def _event(track: object) -> TrackingEvent:
    if not isinstance(track, dict):
        raise _parse_error("track is not an object")
    date_text = track.get("tkDateStr")
    if not isinstance(date_text, str):
        raise _parse_error("track without tkDateStr")
    try:
        naive = datetime.strptime(date_text.strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise _parse_error("unparseable tkDateStr") from exc
    description = clean_text(track.get("tkDesc") or "") or clean_text(
        track.get("tkTranslatedDesc") or ""
    )
    if not description:
        raise _parse_error("track without description")
    code = track.get("tkCode")
    return TrackingEvent(
        time=naive.replace(tzinfo=parse_gmt_offset(track.get("tkTimezone"), _DEFAULT_TZ)),
        description=description,
        location=clean_text(track.get("tkLocation") or "") or None,
        raw_status=str(code) if code else None,
    )


def parse_fourpx_response(payload: object, tracking_number: str) -> TrackingResult:
    if not isinstance(payload, dict) or payload.get("result") != 1:
        raise _parse_error("unexpected result")
    not_found = TrackingResult(carrier="fourpx", tracking_number=tracking_number, found=False)
    data = payload.get("data")
    if data is None or data == []:
        return not_found
    if not isinstance(data, list) or not isinstance(data[0], dict):
        raise _parse_error("data is not a list of objects")
    tracks = data[0].get("tracks")
    if tracks is None or tracks == []:
        return not_found
    if not isinstance(tracks, list):
        raise _parse_error("tracks is not a list")

    result = TrackingResult(
        carrier="fourpx",
        tracking_number=tracking_number,
        found=True,
        events=tuple(_event(track) for track in tracks),
    )
    delivered = (result.latest.raw_status or "").startswith(DELIVERED_CODE_PREFIX)
    return replace(result, delivered=delivered)


class FourPxCarrier:
    code: CarrierCode = "fourpx"
    display_name = "4PX"
    needs_phone = False

    async def fetch(
        self, http: httpx.AsyncClient, tracking_number: str, phone_last4: str | None = None
    ) -> TrackingResult:
        response = await request(
            http,
            "fourpx",
            "POST",
            FOURPX_TRACKING_URL,
            json={
                "queryCodes": [tracking_number],
                "language": "en-us",
                "translateLanguage": "en-us",
            },
        )
        return parse_fourpx_response(json_body("fourpx", response), tracking_number)


MODULE = CarrierModule(
    code="fourpx",
    display_name="4PX",
    order=40,
    rules=(Rule(r"4PX[0-9A-Z]{10,20}", PRIORITY_PREFIXED),),
    examples=(("4PX3000123456789CN", True),),
    build_client=FourPxCarrier,
)
