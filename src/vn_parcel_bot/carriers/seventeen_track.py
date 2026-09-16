from datetime import datetime
from typing import Any

import httpx

from vn_parcel_bot.carriers.common import clean_text, json_body, request
from vn_parcel_bot.carriers.models import CarrierCode, CarrierError, TrackingEvent, TrackingResult

SEVENTEEN_TRACK_BASE = "https://api.17track.net/track/v2.4"
REGISTER_URL = f"{SEVENTEEN_TRACK_BASE}/register"
GET_TRACK_INFO_URL = f"{SEVENTEEN_TRACK_BASE}/gettrackinfo"

# 17TRACK error codes
ERR_ALREADY_REGISTERED = -18019901
ERR_NOT_REGISTERED = -18019902
ERR_QUOTA_EXCEEDED = -18019908

DELIVERED_STATUSES = ("Delivered",)
RETURNED_STATUSES = ("Returned", "ReturnToSender")
RETURNED_SUB_STATUSES = ("Exception_Returning", "Exception_Returned")


class SeventeenTrackCarrier:
    def __init__(
        self,
        carrier_code: CarrierCode,
        display_name: str,
        seventeen_carrier_id: int,
        api_key: str,
        *,
        needs_phone: bool = False,
    ) -> None:
        self.code: CarrierCode = carrier_code
        self.display_name = display_name
        self.needs_phone = needs_phone
        self.seventeen_carrier_id = seventeen_carrier_id
        self._api_key = api_key
        self._headers = {
            "17token": api_key,
            "Content-Type": "application/json",
        }

    async def fetch(
        self,
        http: httpx.AsyncClient,
        tracking_number: str,
        phone_last4: str | None = None,
        *,
        auto_register: bool = True,
    ) -> TrackingResult:
        # Step 1: Query tracking info first (free, 0 quota consumed)
        result = await self._query_track_info(http, tracking_number, phone_last4)
        if result is not None:
            return result

        if not auto_register:
            return TrackingResult(carrier=self.code, tracking_number=tracking_number, found=False)

        # Step 2: Not registered yet (-18019902), register with carrier ID
        await self._register_number(http, tracking_number, phone_last4)

        # Step 3: Re-query after registration
        result = await self._query_track_info(http, tracking_number, phone_last4)
        if result is not None:
            return result

        return TrackingResult(carrier=self.code, tracking_number=tracking_number, found=False)

    def _payload(self, tracking_number: str, phone_last4: str | None) -> list[dict[str, Any]]:
        """17TRACK carries no recipient data of its own: some carriers refuse a number
        unless the last 4 digits of the recipient's phone come with it."""
        item: dict[str, Any] = {"number": tracking_number, "carrier": self.seventeen_carrier_id}
        if phone_last4:
            item["phone_number_last_4"] = phone_last4
        return [item]

    async def _query_track_info(
        self,
        http: httpx.AsyncClient,
        tracking_number: str,
        phone_last4: str | None = None,
    ) -> TrackingResult | None:
        payload = self._payload(tracking_number, phone_last4)
        response = await request(
            http,
            self.code,
            "POST",
            GET_TRACK_INFO_URL,
            headers=self._headers,
            json=payload,
        )
        data = json_body(self.code, response)
        if not isinstance(data, dict) or data.get("code") != 0:
            msg = data.get("message") if isinstance(data, dict) else "invalid format"
            raise CarrierError(self.code, "parse", f"17track gettrackinfo failed: {msg}")

        body = data.get("data")
        if not isinstance(body, dict):
            raise CarrierError(self.code, "parse", "missing data container in 17track response")

        rejected = body.get("rejected") or []
        for item in rejected:
            if not isinstance(item, dict):
                continue
            if item.get("number") == tracking_number:
                error = item.get("error") or {}
                err_code = error.get("code")
                if err_code == ERR_NOT_REGISTERED:
                    return None
                if err_code == ERR_QUOTA_EXCEEDED:
                    raise CarrierError(self.code, "blocked", "17track quota exceeded")
                msg = error.get("message") or f"error {err_code}"
                raise CarrierError(self.code, "parse", f"17track rejected: {msg}")

        accepted = body.get("accepted") or []
        for item in accepted:
            if isinstance(item, dict) and item.get("number") == tracking_number:
                return self._parse_accepted(item, tracking_number)

        return None

    async def _register_number(
        self,
        http: httpx.AsyncClient,
        tracking_number: str,
        phone_last4: str | None = None,
    ) -> None:
        payload = self._payload(tracking_number, phone_last4)
        response = await request(
            http,
            self.code,
            "POST",
            REGISTER_URL,
            headers=self._headers,
            json=payload,
        )
        data = json_body(self.code, response)
        if not isinstance(data, dict) or data.get("code") != 0:
            msg = data.get("message") if isinstance(data, dict) else "invalid format"
            raise CarrierError(self.code, "parse", f"17track register failed: {msg}")

        body = data.get("data")
        if not isinstance(body, dict):
            raise CarrierError(self.code, "parse", "missing data container in register response")

        rejected = body.get("rejected") or []
        for item in rejected:
            if not isinstance(item, dict):
                continue
            if item.get("number") == tracking_number:
                error = item.get("error") or {}
                err_code = error.get("code")
                if err_code == ERR_ALREADY_REGISTERED:
                    return
                if err_code == ERR_QUOTA_EXCEEDED:
                    raise CarrierError(self.code, "blocked", "17track quota exceeded")
                msg = error.get("message") or f"error {err_code}"
                raise CarrierError(self.code, "parse", f"17track register error: {msg}")

    def _parse_accepted(self, item: dict[str, Any], tracking_number: str) -> TrackingResult:
        track_info = item.get("track_info") or {}
        latest_status = item.get("latest_status") or track_info.get("latest_status") or {}
        status = latest_status.get("status") or "NotFound"
        sub_status = latest_status.get("sub_status") or ""

        # Documented shape: track_info.tracking.providers[].events[]; older shapes as fallbacks.
        tracking = track_info.get("tracking") or {}
        providers = tracking.get("providers") or track_info.get("providers") or []

        events: list[TrackingEvent] = []
        raw_events: list[dict[str, Any]] = []
        for provider in providers:
            if isinstance(provider, dict):
                raw_events.extend(provider.get("events") or [])
        if not raw_events:
            raw_events.extend(track_info.get("events") or [])

        for ev in raw_events:
            if not isinstance(ev, dict):
                continue
            time_str = ev.get("time_utc") or ev.get("time_iso")
            if not time_str:
                continue
            try:
                dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            except ValueError:
                continue

            desc = clean_text(ev.get("description") or "")
            if not desc:
                continue

            loc = clean_text(ev.get("location") or "") or None
            stage = ev.get("stage")
            events.append(
                TrackingEvent(
                    time=dt,
                    description=desc,
                    location=loc,
                    raw_status=str(stage) if stage else None,
                )
            )

        found = status != "NotFound" or len(events) > 0
        delivered = status in DELIVERED_STATUSES
        returned = (
            status in RETURNED_STATUSES
            or sub_status in RETURNED_SUB_STATUSES
            or "RETURN" in status.upper()
        )

        return TrackingResult(
            carrier=self.code,
            tracking_number=tracking_number,
            found=found,
            events=tuple(events),
            delivered=delivered,
            returned=returned,
        )
