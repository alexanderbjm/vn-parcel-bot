import html
import math
import re
import urllib.parse
from collections.abc import Mapping, Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from vn_parcel_bot import texts
from vn_parcel_bot.carriers.models import CarrierCode, TrackingEvent
from vn_parcel_bot.carriers.registry import current_snapshot
from vn_parcel_bot.constants import (
    LIST_PAGE_SIZE,
    MAX_EVENTS_IN_HISTORY,
    MAX_EVENTS_IN_UPDATE,
    TELEGRAM_TEXT_LIMIT,
)
from vn_parcel_bot.db.repo import Parcel, User
from vn_parcel_bot.services.parcels import AddOutcome

_INDEX_REF = re.compile(r"\d{1,3}", re.ASCII)


def _escape(value: object) -> str:
    return html.escape(str(value), quote=False)


def spoiler(value: object) -> str:
    return f'<span class="tg-spoiler">{_escape(value)}</span>'


def ref_text(ref: str) -> str:
    return _escape(ref) if _INDEX_REF.fullmatch(ref.strip()) else spoiler(ref)


def parcel_title(parcel: Parcel) -> str:
    """The label, if any, then the blurred tracking code: the code is always shown."""
    code = spoiler(parcel.tracking_number)
    return f"{_escape(parcel.label)} · {code}" if parcel.label else code


SEVENTEEN_TRACK_TEMPLATE = "https://t.17track.net/vi#nums={code}"


def seventeen_track_url(code: str) -> str:
    return SEVENTEEN_TRACK_TEMPLATE.replace("{code}", urllib.parse.quote(code, safe=""))


def carrier_name(code: CarrierCode) -> str:
    return _escape(current_snapshot().display_name(code))


def carrier_names(codes: Sequence[CarrierCode]) -> str:
    return texts.CARRIER_SEPARATOR.join(carrier_name(code) for code in codes)


def parcel_carrier_label(parcel: Parcel) -> str:
    if parcel.carrier is not None:
        return carrier_name(parcel.carrier)
    return carrier_names(parcel.candidates)


def format_time(dt: datetime, tz: ZoneInfo) -> str:
    return dt.astimezone(tz).strftime(texts.TIME_FORMAT)


def progress_bar(percent: int, width: int = 10) -> str:
    filled = max(0, min(width, percent * width // 100))
    return "🟩" * filled + "🟥" * (width - filled)


def _progress_parts(progress: int | None, state: str) -> tuple[str, str]:
    # A delivered parcel keeps "100%" but loses the bar: a full green row is just noise.
    if state == "delivered":
        return texts.PROGRESS_SUFFIX.format(percent=100), ""
    if progress is None or state != "in_transit":
        return "", ""
    return texts.PROGRESS_SUFFIX.format(percent=progress), progress_bar(progress)


def _link_item(url: str, name: str) -> str:
    return texts.LINK_ITEM.format(url=html.escape(url, quote=True), name=name)


def format_links(code: str, carriers: Sequence[CarrierCode]) -> str:
    snapshot = current_snapshot()
    items = []
    for carrier in carriers:
        url = snapshot.link(carrier, code)
        if url is not None:
            items.append(_link_item(url, carrier_name(carrier)))
    items.append(_link_item(seventeen_track_url(code), texts.LINK_17TRACK_NAME))
    return "\n".join(items)


def format_help() -> str:
    snapshot = current_snapshot()
    modules = snapshot.ordered()
    tracked = ", ".join(_escape(m.display_name) for m in modules if snapshot.is_tracked(m.code))
    link_only = ", ".join(
        _escape(m.display_name) for m in modules if not snapshot.is_tracked(m.code)
    )
    return texts.HELP.format(tracked=tracked, link_only=link_only)


def format_link_only(code: str, carriers: Sequence[CarrierCode]) -> str:
    return texts.LINK_ONLY.format(
        code=spoiler(code), carriers=carrier_names(carriers), links=format_links(code, carriers)
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
    progress: int | None = None,
) -> str:
    carrier = carrier_name(resolved_carrier) if resolved_carrier else parcel_carrier_label(parcel)
    state = "delivered" if delivered else "in_transit"
    progress_suffix, bar = _progress_parts(None if returned else progress, state)
    header = texts.UPDATE_HEADER.format(
        title=parcel_title(parcel), carrier=carrier + progress_suffix
    )
    lines = [header]
    if bar:
        lines.append(bar)
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


def _list_item(index: int, parcel: Parcel, tz: ZoneInfo, mark: str = "") -> str:
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
    progress_suffix, bar = _progress_parts(parcel.progress, parcel.state)
    return texts.LIST_ITEM.format(
        index=index,
        emoji=texts.STATE_EMOJI[parcel.state],
        title=parcel_title(parcel),
        carrier=carrier + progress_suffix + mark,
        status=status,
        time_suffix=suffix,
        bar=texts.PROGRESS_BAR_LINE.format(bar=bar) if bar else "",
    )


def format_parcel_card(parcel: Parcel, tz: ZoneInfo, place_line: str | None = None) -> str:
    progress_suffix, bar = _progress_parts(parcel.progress, parcel.state)
    status = (
        _escape(parcel.last_status_text)
        if parcel.last_status_text
        else texts.STATE_TEXT[parcel.state]
    )
    time_suffix = (
        texts.LIST_TIME_SUFFIX.format(time=format_time(parcel.last_event_at, tz))
        if parcel.last_event_at
        else ""
    )
    lines = [
        texts.CARD_HEADER.format(
            emoji=texts.STATE_EMOJI[parcel.state],
            title=parcel_title(parcel),
            carrier=parcel_carrier_label(parcel) + progress_suffix,
        )
    ]
    if bar:
        lines.append(bar)
    lines.append(status + time_suffix)
    if place_line:
        lines.append(place_line)
    return "\n".join(lines)


def parcel_link(parcel: Parcel) -> tuple[str, str]:
    if parcel.carrier is not None:
        snapshot = current_snapshot()
        url = snapshot.link(parcel.carrier, parcel.tracking_number)
        if url:
            return snapshot.display_name(parcel.carrier), url
    return texts.LINK_17TRACK_NAME, seventeen_track_url(parcel.tracking_number)


def list_pages(count: int) -> int:
    return max(1, math.ceil(count / LIST_PAGE_SIZE))


def list_page_items(
    parcels: Sequence[Parcel], page: int
) -> tuple[int, int, list[tuple[int, Parcel]]]:
    pages = list_pages(len(parcels))
    page = min(max(page, 1), pages)
    start = (page - 1) * LIST_PAGE_SIZE
    numbered = list(enumerate(parcels[start : start + LIST_PAGE_SIZE], start=start + 1))
    return page, pages, numbered


def format_parcel_list(parcels: Sequence[Parcel], tz: ZoneInfo, *, page: int = 1) -> str:
    if not parcels:
        return texts.LIST_EMPTY
    page, pages, numbered = list_page_items(parcels, page)
    items = [_list_item(index, parcel, tz) for index, parcel in numbered]
    text = texts.LIST_HEADER + "\n\n" + "\n".join(items)
    if pages > 1:
        text += "\n\n" + texts.LIST_PAGE.format(page=page, pages=pages)
    return truncate_message(text)


def format_check_done(checked: int, new_events: int, redetected: int) -> str:
    text = texts.CHECK_DONE.format(checked=checked, new_events=new_events)
    return text + (texts.CHECK_REDETECTED.format(count=redetected) if redetected else "")


def _remove_items(parcels: Sequence[Parcel]) -> str:
    return "\n".join(texts.REMOVE_ITEM.format(title=parcel_title(p)) for p in parcels)


def format_remove_confirm(parcels: Sequence[Parcel], missing: Sequence[str] = ()) -> str:
    if len(parcels) == 1:
        text = texts.REMOVE_CONFIRM.format(title=parcel_title(parcels[0]))
    else:
        text = texts.REMOVE_CONFIRM_MANY.format(count=len(parcels), items=_remove_items(parcels))
    if missing:
        text += texts.REMOVE_MISSING.format(refs=", ".join(ref_text(ref) for ref in missing))
    return text


def format_removed(parcels: Sequence[Parcel]) -> str:
    if len(parcels) == 1:
        return texts.REMOVED.format(title=parcel_title(parcels[0]))
    return texts.REMOVED_MANY.format(count=len(parcels), items=_remove_items(parcels))


def format_digest(
    parcels: Sequence[Parcel], changed_ids: set[int], at: datetime, tz: ZoneInfo
) -> str:
    items = []
    for index, parcel in enumerate(parcels, start=1):
        is_new = parcel.id in changed_ids or not parcel.is_active
        items.append(_list_item(index, parcel, tz, texts.DIGEST_NEW_MARK if is_new else ""))
    active = sum(1 for parcel in parcels if parcel.is_active)
    finished = len(parcels) - active
    footer = texts.DIGEST_FOOTER.format(active=active)
    if finished:
        footer += texts.DIGEST_FOOTER_FINISHED.format(finished=finished)
    header = texts.DIGEST_HEADER.format(time=at.astimezone(tz).strftime("%H:%M"))
    return truncate_message(header + "\n\n" + "\n".join(items) + "\n\n" + footer)


def format_history(parcel: Parcel, events: Sequence[TrackingEvent], tz: ZoneInfo) -> str:
    header = texts.HISTORY_HEADER.format(
        title=parcel_title(parcel),
        carrier=parcel_carrier_label(parcel),
        code=spoiler(parcel.tracking_number),
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
    snapshot = current_snapshot()
    if any(snapshot.needs_phone(code) for code in parcel.candidates):
        text += texts.ADDED_PENDING_PHONE_HINT
    hint = snapshot.pending_hint(parcel.try_order(), parcel.tracking_number)
    if hint:
        text += hint
    return text + _link_extra(outcome)


def format_add_outcome(outcome: AddOutcome, tz: ZoneInfo, *, max_parcels: int) -> str:
    code = spoiler(outcome.code or "")
    match outcome.kind:
        case "added":
            return _format_added(outcome, tz)
        case "needs_phone":
            asked = texts.ASK_PHONE.format(code=code, carriers=carrier_names(outcome.candidates))
            hint = current_snapshot().pending_hint(outcome.candidates, outcome.code or "")
            return asked + (hint or "")
        case "link_only":
            return format_link_only(outcome.code or "", outcome.link_carriers)
        case "seller_fleet":
            return texts.SELLER_FLEET.format(code=code, links=format_links(outcome.code or "", ()))
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
    return texts.NEEDS_PHONE_MULTI.format(codes="\n".join(spoiler(code) for code in codes))


def format_expired(parcel: Parcel) -> str:
    return texts.EXPIRED.format(code=spoiler(parcel.tracking_number))


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
