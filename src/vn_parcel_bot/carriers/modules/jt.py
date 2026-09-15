import logging
import os
import re
from dataclasses import replace
from datetime import datetime

import httpx
from bs4 import BeautifulSoup, Tag

from vn_parcel_bot.carriers.api import (
    PRIORITY_PREFIXED,
    PRIORITY_SHARED_NUMERIC,
    CarrierModule,
    Rule,
)
from vn_parcel_bot.carriers.common import VN_TZ, clean_text, request
from vn_parcel_bot.carriers.models import CarrierCode, CarrierError, TrackingEvent, TrackingResult
from vn_parcel_bot.carriers.seventeen_track import SeventeenTrackCarrier
from vn_parcel_bot.tracking_codes import mask_code

log = logging.getLogger("vn_parcel_bot.carriers.modules.jt")
JT_TRACKING_URL = "https://jtexpress.vn/tracking"
NOT_FOUND_MARKER = "Không tìm thấy dữ liệu"
DELIVERED_MARKERS = ("giao hàng thành công", "đã ký nhận")
RETURNED_MARKERS = ("hoàn hàng thành công", "đã hoàn hàng", "đã trả hàng cho người gửi")
CROSS_BORDER = re.compile(r"JNTX[A-Z]?\d{8,12}", re.ASCII)
CROSS_BORDER_HINT = (
    "\n🌏 Đây là đơn quốc tế của J&amp;T: J&amp;T VN chỉ có dữ liệu sau khi hàng "
    "thông quan về Việt Nam. Trong lúc chờ, bạn xem hành trình trong app Lazada nhé."
)

RESULT_SELECTOR = ".result-tracking"
BILL_SELECTOR = "[data-billcode]"
EVENT_SELECTOR = ".tracking-event"
TIME_SELECTOR = ".event-time"
DESCRIPTION_SELECTOR = ".event-desc"
LOCATION_SELECTOR = ".event-location"
EMPTY_SELECTOR = ".empty-vandon"
TIME_FORMATS = ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M")


def _parse_error(detail: str) -> CarrierError:
    return CarrierError("jt", "parse", detail)


def _text(node: Tag, selector: str) -> str:
    element = node.select_one(selector)
    return clean_text(element.get_text(" ")) if element is not None else ""


def _parse_time(text: str) -> datetime:
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=VN_TZ)
        except ValueError:
            continue
    raise _parse_error("unparseable event time")


def _matches(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(marker in lowered for marker in markers)


def _event_nodes(soup: BeautifulSoup, tracking_number: str) -> list[Tag]:
    container = soup.select_one(RESULT_SELECTOR)
    if container is None:
        return []
    bills = container.select(BILL_SELECTOR)
    if not bills:
        return container.select(EVENT_SELECTOR)
    for bill in bills:
        if str(bill.get("data-billcode", "")).strip().upper() == tracking_number.upper():
            return bill.select(EVENT_SELECTOR)
    return []


def parse_jt_html(html: str, tracking_number: str) -> TrackingResult:
    soup = BeautifulSoup(html, "html.parser")
    nodes = _event_nodes(soup, tracking_number)
    if not nodes:
        if NOT_FOUND_MARKER in soup.get_text(" ") or soup.select_one(EMPTY_SELECTOR) is not None:
            return TrackingResult(carrier="jt", tracking_number=tracking_number, found=False)
        raise _parse_error("no result or not-found marker")

    events = []
    for node in nodes:
        time_text = _text(node, TIME_SELECTOR)
        description = _text(node, DESCRIPTION_SELECTOR)
        if not time_text or not description:
            raise _parse_error("event without time or description")
        events.append(
            TrackingEvent(
                time=_parse_time(time_text),
                description=description,
                location=_text(node, LOCATION_SELECTOR) or None,
            )
        )

    result = TrackingResult(
        carrier="jt", tracking_number=tracking_number, found=True, events=tuple(events)
    )
    delivered = _matches(result.latest.description, DELIVERED_MARKERS)
    returned = not delivered and any(
        _matches(event.description, RETURNED_MARKERS) for event in result.events
    )
    return replace(result, delivered=delivered, returned=returned)


def _merge_results(domestic: TrackingResult, overseas: TrackingResult) -> TrackingResult:
    seen_keys: set[str] = set()
    merged_events: list[TrackingEvent] = []
    for ev in list(overseas.events) + list(domestic.events):
        if ev.key not in seen_keys:
            seen_keys.add(ev.key)
            merged_events.append(ev)
    merged_events.sort(key=lambda e: e.time)
    delivered = domestic.delivered or overseas.delivered
    returned = domestic.returned or overseas.returned
    return TrackingResult(
        carrier="jt",
        tracking_number=domestic.tracking_number,
        found=True,
        events=tuple(merged_events),
        delivered=delivered,
        returned=returned,
    )


class JtCarrier:
    code: CarrierCode = "jt"
    display_name = "J&T"
    needs_phone = True

    def __init__(self, seventeen_key: str | None = None) -> None:
        self._seventeen_key = seventeen_key

    def _get_seventeen_carrier(self) -> SeventeenTrackCarrier | None:
        key = self._seventeen_key or os.environ.get("SEVENTEEN_TRACK_KEY")
        if not key or not key.strip():
            return None
        return SeventeenTrackCarrier(
            carrier_code="jt",
            display_name="J&T",
            seventeen_carrier_id=100295,
            api_key=key.strip(),
        )

    async def fetch(
        self, http: httpx.AsyncClient, tracking_number: str, phone_last4: str | None = None
    ) -> TrackingResult:
        is_cross_border = bool(CROSS_BORDER.fullmatch(tracking_number))
        seventeen = self._get_seventeen_carrier() if is_cross_border else None

        if not is_cross_border and phone_last4 is None:
            raise ValueError("J&T requires phone_last4")

        # Phase 1: If phone is provided, try domestic tracking on jtexpress.vn
        domestic_result: TrackingResult | None = None
        domestic_error: CarrierError | None = None
        if phone_last4 is not None:
            try:
                response = await request(
                    http,
                    "jt",
                    "GET",
                    JT_TRACKING_URL,
                    params={"type": "track", "billcode": tracking_number, "cellphone": phone_last4},
                )
                domestic_result = parse_jt_html(response.text, tracking_number)
            except CarrierError as err:
                domestic_error = err

        # If domestic is found
        if domestic_result is not None and domestic_result.found:
            # If cross-border and 17TRACK is available, check if overseas events already exist
            # (free query, 0 quota consumed)
            if seventeen is not None:
                try:
                    overseas_result = await seventeen.fetch(
                        http, tracking_number, auto_register=False
                    )
                    if overseas_result.found and overseas_result.events:
                        return _merge_results(domestic_result, overseas_result)
                except CarrierError as err:
                    _log_seventeen_error(err, tracking_number, logging.INFO)
            return domestic_result

        # Phase 2: If cross-border and 17TRACK is available, query/register on 17TRACK
        if seventeen is not None:
            try:
                overseas_result = await seventeen.fetch(http, tracking_number, auto_register=True)
                if overseas_result.found:
                    return overseas_result
                log.info("17track no data carrier=jt code=%s", mask_code(tracking_number))
            except CarrierError as err:
                if domestic_error is None:
                    raise err
                # The J&T VN error is raised below; keep 17TRACK's reason visible too.
                _log_seventeen_error(err, tracking_number, logging.WARNING)

        # If domestic tracking had an error (e.g. network/blocked), propagate it
        if domestic_error is not None:
            raise domestic_error

        # If domestic not-found (or phone was None for cross-border without 17TRACK events)
        if phone_last4 is None and seventeen is None:
            raise ValueError("J&T requires phone_last4")

        return TrackingResult(carrier="jt", tracking_number=tracking_number, found=False)


def _log_seventeen_error(err: CarrierError, tracking_number: str, level: int) -> None:
    masked = mask_code(tracking_number)
    log.log(
        level,
        "17track error carrier=jt reason=%s code=%s detail=%s",
        err.reason,
        masked,
        err.detail.replace(tracking_number, masked),
    )


def cross_border_hint(tracking_number: str) -> str | None:
    return CROSS_BORDER_HINT if CROSS_BORDER.fullmatch(tracking_number) else None


MODULE = CarrierModule(
    code="jt",
    display_name="J&T",
    order=20,
    needs_phone=True,
    rules=(
        Rule(CROSS_BORDER.pattern, PRIORITY_PREFIXED),
        Rule(r"(JTE|JNTVN)[0-9A-Z]{7,14}", PRIORITY_PREFIXED),
        Rule(r"\d{12}", PRIORITY_SHARED_NUMERIC, rank=0),
    ),
    examples=(
        ("JNTXB0000000001", True),
        ("JTE1000000001", True),
        ("841000072647", True),
        ("SPXVN05338454932C", False),
    ),
    build_client=JtCarrier,
    pending_hint=cross_border_hint,
)
