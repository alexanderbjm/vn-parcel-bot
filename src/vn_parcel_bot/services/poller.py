import asyncio
import json
import logging
import random
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Protocol

import httpx

from vn_parcel_bot.carriers.models import CarrierCode, CarrierError, TrackingResult
from vn_parcel_bot.carriers.registry import CarrierRegistry, CarrierSnapshot
from vn_parcel_bot.config import Settings
from vn_parcel_bot.constants import (
    ALERT_COOLDOWN,
    CARRIER_ALL_FAILED_MIN_FETCHES,
    FAILURE_ALERT_THRESHOLD,
    JITTER_SECONDS,
    MAX_BACKOFF,
    PENDING_EXPIRY,
    PURGE_AFTER,
    STALE_AFTER,
)
from vn_parcel_bot.db.repo import Parcel, Repository
from vn_parcel_bot.services.formatting import (
    format_carrier_alert,
    format_event_update,
    format_expired,
    format_stale,
    truncate_message,
)
from vn_parcel_bot.tracking_codes import mask_code

log = logging.getLogger(__name__)

Outcome = TrackingResult | CarrierError


class Notifier(Protocol):
    async def send(self, chat_id: int, text: str, *, silent: bool = False) -> None: ...


@dataclass(frozen=True)
class FetchKey:
    carrier: CarrierCode
    tracking_number: str
    phone_last4: str | None


def fetch_keys(parcel: Parcel, snapshot: CarrierSnapshot) -> list[FetchKey]:
    keys = []
    for carrier in parcel.try_order():
        if snapshot.client(carrier) is None:
            continue
        if snapshot.needs_phone(carrier):
            if parcel.phone_last4:
                keys.append(FetchKey(carrier, parcel.tracking_number, parcel.phone_last4))
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
    ) -> None:
        self._repo = repo
        self._registry = registry
        self._http = http
        self._notifier = notifier
        self._settings = settings
        self._now = now
        self._sleep = sleep
        self._rand = rand
        self._lock = asyncio.Lock()

    async def run_cycle(self, *, only_user_id: int | None = None, wait: bool = False) -> PollReport:
        if self._lock.locked() and not wait:
            now = self._now()
            return PollReport(started_at=now, finished_at=now, skipped=True)
        async with self._lock:
            return await self._cycle(only_user_id)

    def is_quiet(self, at: datetime) -> bool:
        if self._settings.quiet_hours is None:
            return False
        start, end = self._settings.quiet_hours
        hour = at.astimezone(self._settings.tz).hour
        if start < end:
            return start <= hour < end
        return hour >= start or hour < end

    async def _cycle(self, only_user_id: int | None) -> PollReport:
        now = self._now()
        report = PollReport(started_at=now, finished_at=now)
        if only_user_id is None:
            parcels = await self._repo.due_parcels(now)
        else:
            parcels = await self._repo.active_parcels_for_user(only_user_id)
        report.parcels_checked = len(parcels)

        snapshot = self._registry.current
        missing: dict[str, int] = {}
        for parcel in parcels:
            if all(snapshot.get(carrier) is None for carrier in parcel.try_order()):
                for carrier in parcel.try_order():
                    missing[carrier] = missing.get(carrier, 0) + 1
        for carrier, count in sorted(missing.items()):
            log.warning("carrier module missing carrier=%s parcels=%d", carrier, count)

        keys_by_parcel = {parcel.id: fetch_keys(parcel, snapshot) for parcel in parcels}
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
                await self._process(parcel, keys, outcomes, now, report, alerts)
            except Exception:
                log.exception("processing failed code=%s", mask_code(parcel.tracking_number))

        await self._check_stale(processed, now, report)
        self._add_all_failed_alerts(by_carrier, outcomes, alerts)
        await self._send_alerts(alerts, now, report)
        await self._repo.delete_terminal_before(now - PURGE_AFTER)

        report.finished_at = self._now()
        await self._repo.set_meta("last_poll_report", report.to_json())
        if only_user_id is None:
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
    ) -> None:
        current = await self._repo.get_parcel(parcel.id)
        if current is None or not current.is_active:
            return
        parcel = current

        if parcel.is_resolved:
            outcome = outcomes[keys[0]]
            if isinstance(outcome, CarrierError):
                await self._handle_failure(parcel, outcome, now, report, alerts)
            else:
                await self._handle_result(parcel, outcome, now, report, alerts)
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
                    resolved, outcome, now, report, alerts, resolved_carrier=key.carrier
                )
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
    ) -> None:
        interval = self._settings.poll_interval
        if result.found:
            new = await self._repo.insert_events(parcel.id, result.events, now)
            state = (
                "delivered" if result.delivered else "returned" if result.returned else "in_transit"
            )
            newly_delivered = state == "delivered" and parcel.state != "delivered"
            newly_returned = state == "returned" and parcel.state != "returned"
            latest = result.latest
            progress = self._registry.current.progress(result.carrier, result)
            await self._repo.record_check_success(
                parcel.id,
                state=state,
                last_status_text=latest.description if latest else None,
                last_event_at=latest.time if latest else None,
                next_check_at=now + interval,
                now=now,
                delivered_at=latest.time if newly_delivered and latest else None,
                progress=progress,
            )
            report.new_events += len(new)
            if new or newly_delivered or newly_returned:
                text = format_event_update(
                    parcel,
                    new,
                    self._settings.tz,
                    delivered=newly_delivered,
                    returned=newly_returned,
                    resolved_carrier=resolved_carrier,
                    progress=_shown_progress(parcel.progress, progress),
                )
                await self._notify(parcel.user_id, text, report)
            return

        if parcel.carrier is not None and await self._repo.count_events(parcel.id) > 0:
            report.failures[parcel.carrier] = report.failures.get(parcel.carrier, 0) + 1
            error = CarrierError(parcel.carrier, "parse", "events disappeared")
            await self._handle_failure(parcel, error, now, report, alerts)
            return
        if now - parcel.created_at > PENDING_EXPIRY:
            await self._expire(parcel, now, report)
            return
        await self._repo.record_check_success(
            parcel.id,
            state="pending",
            last_status_text=None,
            last_event_at=None,
            next_check_at=now + interval,
            now=now,
        )

    async def _handle_failure(
        self,
        parcel: Parcel,
        error: CarrierError,
        now: datetime,
        report: PollReport,
        alerts: dict[CarrierCode, tuple[int, str]],
    ) -> None:
        if parcel.state == "pending" and now - parcel.created_at > PENDING_EXPIRY:
            await self._expire(parcel, now, report)
            return
        delay = min(
            self._settings.poll_interval * 2 ** (parcel.consecutive_failures + 1), MAX_BACKOFF
        )
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

    async def _notify(
        self, chat_id: int, text: str, report: PollReport, *, silent: bool | None = None
    ) -> None:
        quiet = self.is_quiet(self._now()) if silent is None else silent
        try:
            await self._notifier.send(chat_id, truncate_message(text), silent=quiet)
        except Exception:
            log.warning("notification failed chat=%s", chat_id, exc_info=True)
            return
        report.messages_sent += 1
