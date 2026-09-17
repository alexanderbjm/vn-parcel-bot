import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import httpx

from vn_parcel_bot.carriers.api import PRIORITY_NUMERIC, PRIORITY_PREFIXED, CarrierModule, Rule
from vn_parcel_bot.carriers.common import clean_text, json_body, parse_gmt_offset, request
from vn_parcel_bot.carriers.models import CarrierCode, CarrierError, TrackingEvent, TrackingResult

CAINIAO_TRACKING_URL = "https://global.cainiao.com/global/detail.json"
DELIVERED_ACTION_CODES = ("GTMS_SIGNED",)
RETURNED_ACTION_CODES = ("GTMS_RETURN_SIGNED", "GTMS_RETURN_INBOUND")
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
    mod = module[0]
    dest_mail_no = clean_text(str(mod.get("destMailNo") or ""))
    dest_cp_name = clean_text(str(mod.get("destCpName") or ""))
    dest_cp_code = clean_text(str(mod.get("destCpCode") or ""))

    details = mod.get("detailList")
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
    if dest_mail_no and dest_mail_no != tracking_number and result.events:
        # A separate event dated just before the oldest one keeps the same key on every poll,
        # so the last-mile code is announced once and never becomes the latest event.
        dest_name = dest_cp_name or dest_cp_code or "nội địa"
        handoff = TrackingEvent(
            time=result.events[0].time - timedelta(seconds=1),
            description=f"Chặng cuối {dest_name}: {dest_mail_no}",
            raw_status="DEST_HANDOFF",
        )
        result = replace(result, events=(handoff, *result.events))

    latest_code = result.latest.raw_status or ""
    delivered = latest_code in DELIVERED_ACTION_CODES
    returned = not delivered and (
        latest_code in RETURNED_ACTION_CODES or "RETURN" in latest_code.upper()
    )
    return replace(result, delivered=delivered, returned=returned)


class CainiaoCarrier:
    code: CarrierCode = "cainiao"
    display_name="🦅 Cainiao"
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


LAZADA_WAYBILL = re.compile(r"YT\d{13}", re.ASCII)
LAZADA_HINT = (
    "\n🌏 Đơn quốc tế Lazada qua Cainiao: Cainiao có thể chưa công bố hành trình ngay. "
    "Trong lúc chờ, bạn xem hành trình trong app Lazada nhé."
)


def lazada_hint(tracking_number: str) -> str | None:
    return LAZADA_HINT if LAZADA_WAYBILL.fullmatch(tracking_number) else None


MODULE = CarrierModule(
    code="cainiao",
    display_name="🦅 Cainiao",
    order=30,
    rules=(
        Rule(r"LP\d{14,16}", PRIORITY_PREFIXED),
        Rule(r"[A-Z]{2}\d{9}CN", PRIORITY_PREFIXED),
        Rule(LAZADA_WAYBILL.pattern, PRIORITY_PREFIXED),
        Rule(r"\d{15}", PRIORITY_NUMERIC),
    ),
    examples=(
        ("LP00123456789012", True),
        ("LP0012345678901234", True),
        ("LX123456789CN", True),
        ("YT0000000000001", True),
        ("773440000000001", True),
        ("YT1234567890123456", False),
    ),
    build_client=CainiaoCarrier,
    pending_hint=lazada_hint,
)
