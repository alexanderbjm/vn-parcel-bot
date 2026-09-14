import html
from collections.abc import Mapping, Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from vn_parcel_bot import texts
from vn_parcel_bot.carrier_catalog import (
    CarrierCode,
    needs_phone,
    official_url,
    seventeen_track_url,
)
from vn_parcel_bot.carriers.models import TrackingEvent
from vn_parcel_bot.constants import MAX_EVENTS_IN_HISTORY, MAX_EVENTS_IN_UPDATE, TELEGRAM_TEXT_LIMIT
from vn_parcel_bot.db.repo import Parcel, User
from vn_parcel_bot.services.parcels import AddOutcome


def _escape(value: object) -> str:
    return html.escape(str(value), quote=False)


def parcel_title(parcel: Parcel) -> str:
    return _escape(parcel.label) if parcel.label else _escape(parcel.tracking_number)


def carrier_name(code: CarrierCode) -> str:
    return texts.CARRIER_NAMES[code]


def carrier_names(codes: Sequence[CarrierCode]) -> str:
    return texts.CARRIER_SEPARATOR.join(carrier_name(code) for code in codes)


def parcel_carrier_label(parcel: Parcel) -> str:
    if parcel.carrier is not None:
        return carrier_name(parcel.carrier)
    return carrier_names(parcel.candidates)


def format_time(dt: datetime, tz: ZoneInfo) -> str:
    return dt.astimezone(tz).strftime(texts.TIME_FORMAT)


def _link_item(url: str, name: str) -> str:
    return texts.LINK_ITEM.format(url=html.escape(url, quote=True), name=name)


def format_links(code: str, carriers: Sequence[CarrierCode]) -> str:
    items = []
    for carrier in carriers:
        url = official_url(carrier, code)
        if url is not None:
            items.append(_link_item(url, carrier_name(carrier)))
    items.append(_link_item(seventeen_track_url(code), texts.LINK_17TRACK_NAME))
    return "\n".join(items)


def format_link_only(code: str, carriers: Sequence[CarrierCode]) -> str:
    return texts.LINK_ONLY.format(
        code=_escape(code), carriers=carrier_names(carriers), links=format_links(code, carriers)
    )


def _event_line(event: TrackingEvent, tz: ZoneInfo) -> str:
    line = texts.UPDATE_LINE.format(
        time=format_time(event.time, tz), description=_escape(event.description)
    )
    if event.location:
        line += texts.UPDATE_LOCATION.format(location=_escape(event.location))
    return line


def format_event_update(
    parcel: Parcel,
    new_events: Sequence[TrackingEvent],
    tz: ZoneInfo,
    *,
    delivered: bool,
    returned: bool,
    resolved_carrier: CarrierCode | None = None,
) -> str:
    carrier = carrier_name(resolved_carrier) if resolved_carrier else parcel_carrier_label(parcel)
    lines = [texts.UPDATE_HEADER.format(title=parcel_title(parcel), carrier=carrier)]
    if resolved_carrier:
        lines.append(texts.UPDATE_RESOLVED.format(carrier=carrier))
    ordered = sorted(new_events, key=lambda event: event.time)
    if len(ordered) > MAX_EVENTS_IN_UPDATE:
        lines.append(texts.UPDATE_MORE.format(count=len(ordered) - MAX_EVENTS_IN_UPDATE))
    lines.extend(_event_line(event, tz) for event in ordered[-MAX_EVENTS_IN_UPDATE:])
    if delivered:
        lines.extend(["", texts.UPDATE_DELIVERED])
    elif returned:
        lines.extend(["", texts.UPDATE_RETURNED])
    return truncate_message("\n".join(lines))


def format_parcel_list(parcels: Sequence[Parcel], tz: ZoneInfo) -> str:
    if not parcels:
        return texts.LIST_EMPTY
    items = []
    for index, parcel in enumerate(parcels, start=1):
        status = (
            _escape(parcel.last_status_text)
            if parcel.last_status_text
            else texts.STATE_TEXT[parcel.state]
        )
        suffix = (
            texts.LIST_TIME_SUFFIX.format(time=format_time(parcel.last_event_at, tz))
            if parcel.last_event_at
            else ""
        )
        carrier = (
            carrier_name(parcel.carrier) if parcel.carrier is not None else texts.CARRIER_UNRESOLVED
        )
        items.append(
            texts.LIST_ITEM.format(
                index=index,
                emoji=texts.STATE_EMOJI[parcel.state],
                title=parcel_title(parcel),
                carrier=carrier,
                status=status,
                time_suffix=suffix,
            )
        )
    return truncate_message(texts.LIST_HEADER + "\n\n" + "\n".join(items))


def format_history(parcel: Parcel, events: Sequence[TrackingEvent], tz: ZoneInfo) -> str:
    header = texts.HISTORY_HEADER.format(
        title=parcel_title(parcel),
        carrier=parcel_carrier_label(parcel),
        code=_escape(parcel.tracking_number),
    )
    if not events:
        return header + "\n" + texts.HISTORY_EMPTY
    newest = sorted(events, key=lambda event: event.time, reverse=True)[:MAX_EVENTS_IN_HISTORY]
    return truncate_message(header + "\n" + "\n".join(_event_line(e, tz) for e in newest))


def _link_extra(outcome: AddOutcome) -> str:
    if not outcome.link_carriers:
        return ""
    return texts.LINK_EXTRA.format(
        carriers=carrier_names(outcome.link_carriers),
        links=format_links(outcome.code or "", outcome.link_carriers),
    )


def _format_added(outcome: AddOutcome, tz: ZoneInfo) -> str:
    parcel = outcome.parcel
    if parcel is None:
        raise ValueError("an added outcome needs its parcel")
    title = parcel_title(parcel)
    label = parcel_carrier_label(parcel)
    result = outcome.result
    if result is not None and result.found and result.latest is not None:
        latest = result.latest
        if parcel.state == "delivered":
            return texts.ADDED_DELIVERED.format(
                title=title, carrier=label, time=format_time(latest.time, tz)
            )
        return texts.ADDED_FOUND.format(
            title=title,
            carrier=label,
            status=_escape(latest.description),
            time=format_time(latest.time, tz),
        )
    if outcome.error is not None:
        return texts.ADDED_ERROR.format(title=title, carrier=label) + _link_extra(outcome)
    if parcel.carrier is not None:
        text = texts.ADDED_PENDING.format(title=title, carrier=label)
    else:
        text = texts.ADDED_PENDING_AUTO.format(title=title, carriers=label)
    if any(needs_phone(code) for code in parcel.candidates):
        text += texts.ADDED_PENDING_PHONE_HINT
    return text + _link_extra(outcome)


def format_add_outcome(outcome: AddOutcome, tz: ZoneInfo, *, max_parcels: int) -> str:
    code = _escape(outcome.code or "")
    match outcome.kind:
        case "added":
            return _format_added(outcome, tz)
        case "needs_phone":
            return texts.ASK_PHONE.format(code=code, carriers=carrier_names(outcome.candidates))
        case "link_only":
            return format_link_only(outcome.code or "", outcome.link_carriers)
        case "seller_fleet":
            return texts.SELLER_FLEET.format(code=code, links=format_links(outcome.code or "", ()))
        case "order_number":
            return texts.ORDER_NUMBER.format(code=code, links=format_links(outcome.code or "", ()))
        case "unknown_carrier":
            return texts.UNKNOWN_CARRIER.format(
                code=code, links=format_links(outcome.code or "", ())
            )
        case "duplicate":
            return texts.DUPLICATE.format(code=code)
        case "limit":
            return texts.LIMIT_REACHED.format(max=max_parcels)
        case "invalid_phone":
            return texts.INVALID_PHONE
        case _:
            return texts.UNKNOWN_CODE


def format_needs_phone_multi(codes: Sequence[str]) -> str:
    return texts.NEEDS_PHONE_MULTI.format(
        codes="\n".join(f"<code>{_escape(code)}</code>" for code in codes)
    )


def format_expired(parcel: Parcel) -> str:
    return texts.EXPIRED.format(code=_escape(parcel.tracking_number))


def format_stale(parcel: Parcel) -> str:
    return texts.STALE.format(title=parcel_title(parcel))


def format_carrier_alert(carrier: CarrierCode, count: int, detail: str) -> str:
    return texts.ALERT_CARRIER.format(
        carrier=carrier_name(carrier), count=count, detail=_escape(detail[:200])
    )


def format_users(users: Sequence[User], active_counts: Mapping[int, int], admin_id: int) -> str:
    lines = [texts.USERS_HEADER]
    for user in users:
        if user.telegram_id == admin_id:
            role = texts.ROLE_ADMIN
        elif user.is_allowed:
            role = texts.ROLE_MEMBER
        else:
            role = texts.ROLE_BLOCKED
        lines.append(
            texts.USERS_ITEM.format(
                user_id=user.telegram_id,
                name=_escape(user.name) if user.name else "—",
                role=role,
                active=active_counts.get(user.telegram_id, 0),
            )
        )
    return truncate_message("\n".join(lines))


def format_health(
    last_poll_at: datetime | None,
    report: dict | None,
    active: int,
    users: int,
    tz: ZoneInfo,
) -> str:
    report = report or {}
    failures = report.get("failures") or {}
    failures_text = ", ".join(f"{name}={count}" for name, count in failures.items()) or "0"
    return texts.HEALTH.format(
        last_poll=format_time(last_poll_at, tz) if last_poll_at else texts.HEALTH_NEVER,
        active=active,
        users=users,
        fetches=report.get("fetches", 0),
        new_events=report.get("new_events", 0),
        failures=_escape(failures_text),
    )


def truncate_message(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> str:
    if len(text) <= limit:
        return text
    cut = text.rfind("\n", 0, limit - 1)
    head = text[:cut] if cut > 0 else text[: limit - 1]
    return head + "…"
