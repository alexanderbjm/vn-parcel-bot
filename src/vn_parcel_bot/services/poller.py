import asyncio
import json
import logging
import random
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Protocol

import httpx

from vn_parcel_bot.carriers.models import (
    CarrierCode,
    CarrierError,
    TrackingEvent,
    TrackingResult,
)
from vn_parcel_bot.carriers.registry import CarrierRegistry, CarrierSnapshot
from vn_parcel_bot.carriers.seventeen_track import SeventeenTrackCarrier
from vn_parcel_bot.config import Settings
from vn_parcel_bot.constants import (
    ALERT_COOLDOWN,
    CARRIER_ALL_FAILED_MIN_FETCHES,
    DELIVERED_VISIBLE_FOR,
    FAILURE_ALERT_THRESHOLD,
    JITTER_SECONDS,
    MAX_BACKOFF,
    OUT_FOR_DELIVERY_PROGRESS,
    PENDING_EXPIRY,
    PURGE_AFTER,
    STALE_AFTER,
)
from vn_parcel_bot.db.repo import Parcel, Repository, User
from vn_parcel_bot.keyboards import card_keyboard
from vn_parcel_bot.services.formatting import (
    format_carrier_alert,
    format_event_update,
    format_expired,
    format_stale,
    truncate_message,
)
from vn_parcel_bot.services.maps import MapError
from vn_parcel_bot.services.parcel_maps import ParcelMaps
from vn_parcel_bot.services.scheduling import check_interval
from vn_parcel_bot.tracking_codes import mask_code

log = logging.getLogger(__name__)

Outcome = TrackingResult | CarrierError


class Notifier(Protocol):
    async def send(
        self, chat_id: int, text: str, *, silent: bool = False, reply_markup: object = None
    ) -> None: ...

    async def send_sticker(self, chat_id: int, file_id: str) -> bool: ...

    async def send_photo(
        self, chat_id: int, photo: bytes, caption: str, *, silent: bool = False
    ) -> None: ...


@dataclass(frozen=True)
class FetchKey:
    carrier: CarrierCode
    tracking_number: str
    phone_last4: str | None


def fetch_keys(
    parcel: Parcel,
    snapshot: CarrierSnapshot,
    default_phone_last4: str | None = None,
) -> list[FetchKey]:
    """The calls to make for one parcel.

    A carrier that needs the recipient's digits is skipped without them, so a parcel stored
    before its owner saved a default would otherwise never be polled again. Fall back to the
    owner's saved digits, exactly as ``ParcelService.add`` does, so setting /phone revives it.
    """
    keys = []
    for carrier in parcel.try_order():
        if snapshot.client(carrier) is None:
            continue
        if snapshot.needs_phone(carrier):
            digits = parcel.phone_last4 or default_phone_last4
            if digits:
                keys.append(FetchKey(carrier, parcel.tracking_number, digits))
        else:
            keys.append(FetchKey(carrier, parcel.tracking_number, None))
    return keys


def _shown_progress(stored: int | None, new: int | None) -> int | None:
    if new is None:
        return stored
    return max(new, stored or 0)


@dataclass
class PollReport:
    started_at: datetime
    finished_at: datetime
    skipped: bool = False
    parcels_checked: int = 0
    fetches: int = 0
    new_events: int = 0
    messages_sent: int = 0
    rebuilt: int = 0
    failures: dict[str, int] = field(default_factory=dict)

    def to_json(self) -> str:
        data = asdict(self)
        data["started_at"] = self.started_at.isoformat()
        data["finished_at"] = self.finished_at.isoformat()
        return json.dumps(data, ensure_ascii=False)


class Poller:
    def __init__(
        self,
        repo: Repository,
        registry: CarrierRegistry,
        http: httpx.AsyncClient,
        notifier: Notifier,
        settings: Settings,
        now: Callable[[], datetime],
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rand: Callable[[], float] = random.random,
        maps: ParcelMaps | None = None,
        seventeen: object | None = None,
    ) -> None:
        self._repo = repo
        self._registry = registry
        self._http = http
        self._notifier = notifier
        self._settings = settings
        self._now = now
        self._sleep = sleep
        self._rand = rand
        self._maps = maps
        self._seventeen = seventeen
        self._lock = asyncio.Lock()
        self._broken_stickers: set[str] = set()

    async def run_cycle(
        self, *, only_user_id: int | None = None, wait: bool = False, rebuild: bool = False
    ) -> PollReport:
        """Check due parcels, or one user's parcels now.

        `rebuild` (a user's Kiểm tra) also takes the user's recently finished parcels, resets
        failure counts and replaces each parcel's stored history, progress and hub with a fresh
        read; only events newer than the stored history are sent as updates.
        """
        if self._lock.locked() and not wait:
            now = self._now()
            return PollReport(started_at=now, finished_at=now, skipped=True)
        async with self._lock:
            return await self._cycle(only_user_id, rebuild=rebuild)

    async def check_parcel(
        self, user_id: int, parcel_id: int, *, rebuild: bool = False
    ) -> Parcel | None:
        async with self._lock:
            parcel = await self._repo.get_parcel(parcel_id)
            if parcel is None or parcel.user_id != user_id:
                return None
            if parcel.is_active or rebuild:
                await self._cycle(None, only_parcels=[parcel], rebuild=rebuild)
            return await self._repo.get_parcel(parcel_id)

    def is_quiet(self, at: datetime) -> bool:
        if self._settings.quiet_hours is None:
            return False
        start, end = self._settings.quiet_hours
        hour = at.astimezone(self._settings.tz).hour
        if start < end:
            return start <= hour < end
        return hour >= start or hour < end

    async def _cycle(
        self,
        only_user_id: int | None,
        only_parcels: list[Parcel] | None = None,
        *,
        rebuild: bool = False,
    ) -> PollReport:
        now = self._now()
        report = PollReport(started_at=now, finished_at=now)
        if only_parcels is not None:
            parcels = only_parcels
        elif only_user_id is None:
            parcels = await self._repo.due_parcels(now)
        elif rebuild:
            parcels = await self._repo.list_parcels(
                only_user_id, terminal_since=now - DELIVERED_VISIBLE_FOR
            )
        else:
            parcels = await self._repo.active_parcels_for_user(only_user_id)
        if rebuild:
            await self._repo.reset_failures([parcel.id for parcel in parcels])
        report.parcels_checked = len(parcels)
        if not parcels and only_user_id is None and only_parcels is None:
            # The poll job ticks every minute; an idle tick only purges and records that it ran.
            await self._repo.delete_terminal_before(now - PURGE_AFTER)
            await self._repo.set_meta("last_poll_at", now.isoformat())
            return report

        snapshot = self._registry.current
        missing: dict[str, int] = {}
        for parcel in parcels:
            if all(snapshot.get(carrier) is None for carrier in parcel.try_order()):
                for carrier in parcel.try_order():
                    missing[carrier] = missing.get(carrier, 0) + 1
        for carrier, count in sorted(missing.items()):
            log.warning("carrier module missing carrier=%s parcels=%d", carrier, count)

        defaults = {
            user.telegram_id: user.default_phone_last4 for user in await self._repo.list_users()
        }
        keys_by_parcel = {
            parcel.id: fetch_keys(parcel, snapshot, defaults.get(parcel.user_id))
            for parcel in parcels
        }
        stranded = [
            parcel
            for parcel in parcels
            if not keys_by_parcel[parcel.id]
            and any(snapshot.needs_phone(carrier) for carrier in parcel.try_order())
        ]
        if stranded:
            # Otherwise these sit in /list as pending forever, with nothing in the logs.
            log.warning(
                "parcels awaiting saved phone digits parcels=%d (set them with /phone)",
                len(stranded),
            )
        by_carrier: dict[CarrierCode, list[FetchKey]] = {}
        for parcel in parcels:
            for key in keys_by_parcel[parcel.id]:
                carrier_keys = by_carrier.setdefault(key.carrier, [])
                if key not in carrier_keys:
                    carrier_keys.append(key)

        outcomes: dict[FetchKey, Outcome] = {}
        await asyncio.gather(
            *(
                self._fetch_carrier(snapshot, carrier, keys, outcomes, report)
                for carrier, keys in by_carrier.items()
            )
        )

        alerts: dict[CarrierCode, tuple[int, str]] = {}
        processed: list[int] = []
        for parcel in parcels:
            keys = keys_by_parcel[parcel.id]
            if not keys:
                continue
            processed.append(parcel.id)
            try:
                await self._process(parcel, keys, outcomes, now, report, alerts, rebuild=rebuild)
            except Exception:
                log.exception("processing failed code=%s", mask_code(parcel.tracking_number))

        await self._check_stale(processed, now, report)
        self._add_all_failed_alerts(by_carrier, outcomes, alerts)
        await self._send_alerts(alerts, now, report)
        await self._repo.delete_terminal_before(now - PURGE_AFTER)

        report.finished_at = self._now()
        await self._repo.set_meta("last_poll_report", report.to_json())
        if only_user_id is None and only_parcels is None:
            await self._repo.set_meta("last_poll_at", report.finished_at.isoformat())
        log.info(
            "poll cycle parcels=%s fetches=%s new_events=%s messages=%s failures=%s",
            report.parcels_checked,
            report.fetches,
            report.new_events,
            report.messages_sent,
            report.failures,
        )
        return report

    async def _fetch_carrier(
        self,
        snapshot: CarrierSnapshot,
        code: CarrierCode,
        keys: Sequence[FetchKey],
        outcomes: dict[FetchKey, Outcome],
        report: PollReport,
    ) -> None:
        carrier = snapshot.client(code)
        if carrier is None:
            return
        for index, key in enumerate(keys):
            if index > 0:
                await self._sleep(
                    self._settings.request_delay_seconds + self._rand() * JITTER_SECONDS
                )
            report.fetches += 1
            try:
                outcomes[key] = await carrier.fetch(
                    self._http, key.tracking_number, key.phone_last4
                )
                continue
            except CarrierError as err:
                error = err
            except Exception as exc:
                log.exception(
                    "carrier crashed carrier=%s code=%s", code, mask_code(key.tracking_number)
                )
                error = CarrierError(code, "parse", type(exc).__name__)
            outcomes[key] = error
            report.failures[code] = report.failures.get(code, 0) + 1
            log.warning(
                "carrier error carrier=%s reason=%s code=%s detail=%s",
                code,
                error.reason,
                mask_code(key.tracking_number),
                error.detail,
            )

    async def _process(
        self,
        parcel: Parcel,
        keys: Sequence[FetchKey],
        outcomes: Mapping[FetchKey, Outcome],
        now: datetime,
        report: PollReport,
        alerts: dict[CarrierCode, tuple[int, str]],
        *,
        rebuild: bool = False,
    ) -> None:
        current = await self._repo.get_parcel(parcel.id)
        if current is None or not (current.is_active or rebuild):
            return
        parcel = current
        # A finished parcel is only rebuilt from fresh data; errors and empty answers leave it.
        finished = not parcel.is_active

        if parcel.is_resolved:
            outcome = outcomes[keys[0]]
            if finished and (isinstance(outcome, CarrierError) or not outcome.found):
                return
            if isinstance(outcome, CarrierError):
                await self._handle_failure(parcel, outcome, now, report, alerts)
            else:
                await self._handle_result(parcel, outcome, now, report, alerts, rebuild=rebuild)
            return

        results = [(key, outcomes[key]) for key in keys]
        for key, outcome in results:
            if isinstance(outcome, TrackingResult) and outcome.found:
                await self._repo.resolve_carrier(parcel.id, key.carrier, now)
                resolved = await self._repo.get_parcel(parcel.id)
                if resolved is None:
                    return
                log.info(
                    "carrier resolved carrier=%s code=%s",
                    key.carrier,
                    mask_code(parcel.tracking_number),
                )
                await self._handle_result(
                    resolved,
                    outcome,
                    now,
                    report,
                    alerts,
                    resolved_carrier=key.carrier,
                    rebuild=rebuild,
                )
                return
        if finished:
            return
        errors = [outcome for _, outcome in results if isinstance(outcome, CarrierError)]
        if errors:
            await self._handle_failure(parcel, errors[0], now, report, alerts)
            return
        first = results[0][1]
        assert isinstance(first, TrackingResult)
        await self._handle_result(parcel, first, now, report, alerts)

    async def _handle_result(
        self,
        parcel: Parcel,
        result: TrackingResult,
        now: datetime,
        report: PollReport,
        alerts: dict[CarrierCode, tuple[int, str]],
        *,
        resolved_carrier: CarrierCode | None = None,
        rebuild: bool = False,
    ) -> None:
        if result.found:
            if rebuild:
                new = await self._replace_history(parcel, result, now)
                report.rebuilt += 1
            else:
                new = await self._repo.insert_events(parcel.id, result.events, now)
            state = (
                "delivered" if result.delivered else "returned" if result.returned else "in_transit"
            )
            newly_delivered = state == "delivered" and parcel.state != "delivered"
            newly_returned = state == "returned" and parcel.state != "returned"
            latest = result.latest
            progress = self._registry.current.progress(result.carrier, result)
            shown = progress if rebuild else _shown_progress(parcel.progress, progress)
            interval = check_interval(state, shown, self._settings.poll_interval)
            await self._repo.record_check_success(
                parcel.id,
                state=state,
                last_status_text=latest.description if latest else None,
                last_event_at=latest.time if latest else None,
                next_check_at=now + interval,
                now=now,
                delivered_at=latest.time if newly_delivered and latest else None,
                progress=progress,
                reset_progress=rebuild,
            )
            moved = await self._track_place(parcel, result, rebuild=rebuild)
            report.new_events += len(new)
            if new or newly_delivered or newly_returned:
                current = await self._repo.get_parcel(parcel.id)
                user = await self._repo.get_user(parcel.user_id)
                place_line = (
                    await self._maps.place_line(current, user)
                    if self._maps is not None and current is not None and user is not None
                    else None
                )
                text = format_event_update(
                    parcel,
                    new,
                    self._settings.tz,
                    delivered=newly_delivered,
                    returned=newly_returned,
                    resolved_carrier=resolved_carrier,
                    progress=shown,
                    place_line=place_line,
                )
                reached = (
                    progress is not None
                    and progress >= OUT_FOR_DELIVERY_PROGRESS
                    and (parcel.progress or 0) < OUT_FOR_DELIVERY_PROGRESS
                )
                big_moment = newly_delivered or newly_returned or reached
                await self._send_sticker(parcel.user_id, result.carrier)
                await self._notify(
                    parcel.user_id,
                    text,
                    report,
                    silent=None if big_moment else True,
                    reply_markup=(
                        card_keyboard(current, maps=self._maps_on) if current is not None else None
                    ),
                )
                if moved and current is not None and user is not None:
                    await self._send_map(current, user)
            return

        if parcel.carrier is not None and await self._repo.count_events(parcel.id) > 0:
            report.failures[parcel.carrier] = report.failures.get(parcel.carrier, 0) + 1
            error = CarrierError(parcel.carrier, "parse", "events disappeared")
            await self._handle_failure(parcel, error, now, report, alerts)
            return
        if await self._seventeen_fallback(parcel, now, report, alerts):
            return
        if now - parcel.created_at > PENDING_EXPIRY:
            await self._expire(parcel, now, report)
            return
        await self._repo.record_check_success(
            parcel.id,
            state="pending",
            last_status_text=None,
            last_event_at=None,
            next_check_at=now + self._settings.poll_interval,
            now=now,
        )

    async def _seventeen_fallback(
        self,
        parcel: Parcel,
        now: datetime,
        report: PollReport,
        alerts: dict[CarrierCode, tuple[int, str]],
        *,
        register: bool = True,
    ) -> bool:
        """Ask 17TRACK about a parcel our own carriers cannot track.

        17TRACK identifies the carrier itself, so a code that belongs to a carrier without a
        module (STO, YT, China Post...) still gets a history. Registering costs one quota, so
        it happens once per parcel and is recorded in `meta`; afterwards each poll re-queries
        for free, and data appears as soon as 17TRACK has it. Running out of quota records
        nothing, so the parcel can still be registered later.

        `register=False` re-queries a parcel that is already registered and does nothing
        otherwise, so a carrier having a bad day never costs a registration.
        """
        if self._seventeen is None or not self._settings.seventeen_fallback:
            return False
        key = f"17track-tried:{parcel.id}"
        registered = await self._repo.get_meta(key) is not None
        if not registered and not register:
            return False
        masked = mask_code(parcel.tracking_number)
        try:
            result = await self._seventeen.fetch(
                self._http,
                parcel.tracking_number,
                parcel.phone_last4,
                auto_register=not registered,
            )
        except CarrierError as exc:
            if exc.reason == "blocked":
                # Out of registration quota: leave the parcel unregistered and try another day.
                log.warning("17track fallback out of quota code=%s", masked)
                return False
            if not registered:
                await self._repo.set_meta(key, now.isoformat())
            log.warning("17track fallback failed code=%s reason=%s", masked, exc.reason)
            return False
        except Exception as exc:
            if not registered:
                await self._repo.set_meta(key, now.isoformat())
            log.warning("17track fallback failed code=%s type=%s", masked, type(exc).__name__)
            return False
        if not registered:
            await self._repo.set_meta(key, now.isoformat())
        if not result.found:
            log.info("17track fallback has no data code=%s", masked)
            return False
        log.info("17track fallback found data code=%s events=%s", masked, len(result.events))
        await self._handle_result(parcel, result, now, report, alerts)
        return True

    @property
    def _maps_on(self) -> bool:
        return self._maps is not None and self._settings.maps_enabled

    async def _replace_history(
        self, parcel: Parcel, result: TrackingResult, now: datetime
    ) -> list[TrackingEvent]:
        """Store the fresh history; return only events newer than anything stored before."""
        known = await self._repo.event_keys(parcel.id)
        await self._repo.replace_events(parcel.id, result.events, now)
        since = parcel.last_event_at
        fresh = {event.key: event for event in sorted(result.events, key=lambda e: e.time)}
        return [
            event
            for key, event in fresh.items()
            if key not in known and (since is None or event.time > since)
        ]

    async def _track_place(
        self, parcel: Parcel, result: TrackingResult, *, rebuild: bool = False
    ) -> bool:
        """Store the newest hub; True when it changed. Lookup failures never stop the update.

        A rebuild also clears a stored hub that the fresh read no longer shows.
        """
        if self._maps is None:
            return False
        place = self._registry.current.latest_place(result.carrier, result.events)
        if rebuild and place is None and parcel.place is not None:
            await self._repo.set_place(parcel.id, None)
            return False
        if place is None or place == parcel.place:
            return False
        await self._repo.set_place(parcel.id, place)
        try:
            await self._maps.prepare(place)
        except Exception as exc:
            log.warning("place lookup failed type=%s", type(exc).__name__)
        return True

    async def _send_map(self, parcel: Parcel, user: User) -> None:
        if self._maps is None:
            return
        try:
            made = await self._maps.photo(parcel, user)
        except MapError as exc:
            log.warning("map failed type=%s", type(exc).__name__)
            return
        if made is None:
            return
        try:
            await self._notifier.send_photo(parcel.user_id, made[0], made[1], silent=True)
        except Exception as exc:
            log.warning("map send failed type=%s", type(exc).__name__)

    async def _handle_failure(
        self,
        parcel: Parcel,
        error: CarrierError,
        now: datetime,
        report: PollReport,
        alerts: dict[CarrierCode, tuple[int, str]],
    ) -> None:
        # The parcel's own carrier is failing, so 17TRACK answers instead when it already
        # tracks this parcel. Without this a carrier that keeps erroring freezes the parcel.
        if await self._seventeen_fallback(parcel, now, report, alerts, register=False):
            return
        if parcel.state == "pending" and now - parcel.created_at > PENDING_EXPIRY:
            await self._expire(parcel, now, report)
            return
        base = check_interval(parcel.state, parcel.progress, self._settings.poll_interval)
        delay = min(base * 2 ** (parcel.consecutive_failures + 1), MAX_BACKOFF)
        failures = await self._repo.record_check_failure(
            parcel.id, next_check_at=now + delay, now=now
        )
        if failures == FAILURE_ALERT_THRESHOLD:
            alerts[error.carrier] = (failures, str(error))

    async def _expire(self, parcel: Parcel, now: datetime, report: PollReport) -> None:
        await self._repo.set_state(parcel.id, "expired", now)
        await self._notify(parcel.user_id, format_expired(parcel), report)
        log.info("parcel expired code=%s", mask_code(parcel.tracking_number))

    async def _check_stale(
        self, parcel_ids: Sequence[int], now: datetime, report: PollReport
    ) -> None:
        for parcel_id in parcel_ids:
            parcel = await self._repo.get_parcel(parcel_id)
            if (
                parcel is not None
                and parcel.state == "in_transit"
                and parcel.last_event_at is not None
                and parcel.last_event_at < now - STALE_AFTER
            ):
                await self._repo.set_state(parcel.id, "stale", now)
                await self._notify(parcel.user_id, format_stale(parcel), report)

    @staticmethod
    def _add_all_failed_alerts(
        by_carrier: Mapping[CarrierCode, Sequence[FetchKey]],
        outcomes: Mapping[FetchKey, Outcome],
        alerts: dict[CarrierCode, tuple[int, str]],
    ) -> None:
        for carrier, keys in by_carrier.items():
            errors = [outcomes[k] for k in keys if isinstance(outcomes.get(k), CarrierError)]
            if (
                carrier not in alerts
                and len(keys) >= CARRIER_ALL_FAILED_MIN_FETCHES
                and len(errors) == len(keys)
            ):
                alerts[carrier] = (len(errors), str(errors[-1]))

    async def _send_alerts(
        self, alerts: Mapping[CarrierCode, tuple[int, str]], now: datetime, report: PollReport
    ) -> None:
        for carrier, (count, detail) in alerts.items():
            meta_key = f"alert:{carrier}"
            last = await self._repo.get_meta(meta_key)
            if last is not None and now - datetime.fromisoformat(last) < ALERT_COOLDOWN:
                continue
            text = format_carrier_alert(carrier, count, detail)
            await self._notify(self._settings.admin_telegram_id, text, report, silent=False)
            await self._repo.set_meta(meta_key, now.isoformat())

    async def _send_sticker(self, chat_id: int, carrier: str) -> None:
        if carrier in self._broken_stickers:
            return
        file_id = await self._repo.get_meta(f"sticker:{carrier}")
        if not file_id:
            return
        try:
            ok = await self._notifier.send_sticker(chat_id, file_id)
        except Exception:
            ok = False
        if not ok:
            self._broken_stickers.add(carrier)
            log.warning("carrier sticker failed carrier=%s", carrier)

    async def _notify(
        self,
        chat_id: int,
        text: str,
        report: PollReport,
        *,
        silent: bool | None = None,
        reply_markup: object = None,
    ) -> None:
        quiet = self.is_quiet(self._now()) if silent is None else silent
        try:
            await self._notifier.send(
                chat_id, truncate_message(text), silent=quiet, reply_markup=reply_markup
            )
        except Exception:
            log.warning("notification failed chat=%s", chat_id, exc_info=True)
            return
        report.messages_sent += 1


def build_seventeen(settings: Settings) -> SeventeenTrackCarrier | None:
    """The 17TRACK client used as a last resort, or None when it is off or has no key."""
    key = (settings.seventeen_track_key or "").strip()
    if not key or not settings.seventeen_fallback:
        return None
    return SeventeenTrackCarrier(
        carrier_code="17track",
        display_name="17TRACK",
        seventeen_carrier_id=None,
        api_key=key,
    )
