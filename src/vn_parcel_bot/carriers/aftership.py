"""AfterShip as a tracking source, alongside 17TRACK.

Same shape as seventeen_track.py on purpose: the poller treats every aggregator alike, so
each one exposes fetch() and reports running out of allowance as a "blocked" CarrierError.
"""

from datetime import datetime
from typing import Any

import httpx

from vn_parcel_bot.carriers.common import clean_text, json_body, request
from vn_parcel_bot.carriers.models import CarrierCode, CarrierError, TrackingEvent, TrackingResult
from vn_parcel_bot.carriers.translate_cn import translate_cn

AFTERSHIP_BASE = "https://api.aftership.com/v4"
TRACKINGS_URL = f"{AFTERSHIP_BASE}/trackings"

# AfterShip's own vocabulary for where a parcel has got to.
DELIVERED_TAGS = ("Delivered",)
RETURNED_TAGS = ("Exception", "AvailableForPickup")
RETURNED_WORDS = ("hoàn", "return", "trả lại")


def _event_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class AfterShipCarrier:
    """Reads a tracking from AfterShip. Creating one costs a shipment from the plan."""

    code: CarrierCode = "aftership"
    display_name = "AfterShip"
    needs_phone = False

    def __init__(self, api_key: str) -> None:
        self._headers = {"aftership-api-key": api_key, "Content-Type": "application/json"}

    async def fetch(
        self,
        http: httpx.AsyncClient,
        tracking_number: str,
        phone_last4: str | None = None,
        *,
        auto_register: bool = True,
    ) -> TrackingResult:
        """Read what AfterShip knows; with auto_register, ask it to start tracking first.

        phone_last4 is accepted so every aggregator has one signature; AfterShip does not use it.
        """
        result = await self._read(http, tracking_number)
        if result is not None:
            return result
        if not auto_register:
            return TrackingResult(carrier=self.code, tracking_number=tracking_number, found=False)
        await self._create(http, tracking_number)
        result = await self._read(http, tracking_number)
        if result is not None:
            return result
        return TrackingResult(carrier=self.code, tracking_number=tracking_number, found=False)

    async def _read(self, http: httpx.AsyncClient, tracking_number: str) -> TrackingResult | None:
        response = await request(
            http,
            self.code,
            "GET",
            f"{TRACKINGS_URL}/{tracking_number}",
            headers=self._headers,
            not_found_statuses=(404,),
        )
        if response.status_code == 404:
            return None
        return self._parse(json_body(self.code, response), tracking_number)

    async def _create(self, http: httpx.AsyncClient, tracking_number: str) -> None:
        response = await request(
            http,
            self.code,
            "POST",
            TRACKINGS_URL,
            headers=self._headers,
            json={"tracking": {"tracking_number": tracking_number}},
            not_found_statuses=(409,),
        )
        if response.status_code == 409:
            # Already tracked: nothing to do, the read that follows will find it.
            return
        json_body(self.code, response)

    def _parse(self, data: Any, tracking_number: str) -> TrackingResult:
        if not isinstance(data, dict):
            raise CarrierError(self.code, "parse", "aftership: response is not an object")
        body = data.get("data")
        tracking = body.get("tracking") if isinstance(body, dict) else None
        if not isinstance(tracking, dict):
            raise CarrierError(self.code, "parse", "aftership: missing tracking container")

        tag = str(tracking.get("tag") or "")
        events: list[TrackingEvent] = []
        for checkpoint in tracking.get("checkpoints") or []:
            if not isinstance(checkpoint, dict):
                continue
            moment = _event_time(checkpoint.get("checkpoint_time"))
            if moment is None or moment.tzinfo is None:
                continue
            said = clean_text(checkpoint.get("message") or "")
            if not said:
                continue
            where = clean_text(checkpoint.get("location") or "")
            events.append(
                TrackingEvent(
                    time=moment,
                    description=translate_cn(said),
                    location=translate_cn(where) or None,
                    raw_status=tag or None,
                    # AfterShip's own wording, so a better translation never re-creates events.
                    identity=f"{said}|{where}",
                )
            )

        latest = max(events, key=lambda event: event.time).description.casefold() if events else ""
        returned = tag in RETURNED_TAGS and any(word in latest for word in RETURNED_WORDS)
        return TrackingResult(
            carrier=self.code,
            tracking_number=tracking_number,
            found=bool(events),
            events=tuple(events),
            delivered=tag in DELIVERED_TAGS,
            returned=returned,
        )
