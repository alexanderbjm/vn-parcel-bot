import logging
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import httpx

from vn_parcel_bot.carrier_catalog import CarrierCode, is_tracked, needs_phone
from vn_parcel_bot.carriers.models import Carrier, CarrierError, TrackingEvent, TrackingResult
from vn_parcel_bot.config import Settings
from vn_parcel_bot.constants import (
    DELIVERED_VISIBLE_FOR,
    MAX_BACKOFF,
    MAX_EVENTS_IN_HISTORY,
    MAX_LABEL_LENGTH,
)
from vn_parcel_bot.db.repo import DuplicateParcelError, Parcel, Repository, User
from vn_parcel_bot.tracking_codes import (
    GENERIC_CODE_RE,
    detect_carriers,
    is_valid_last4,
    mask_code,
    normalize_code,
)

log = logging.getLogger(__name__)

AddKind = Literal[
    "added", "needs_phone", "link_only", "duplicate", "limit", "invalid_code", "invalid_phone"
]

_INDEX_REF = re.compile(r"\d{1,3}", re.ASCII)

Attempt = tuple[CarrierCode, TrackingResult | CarrierError]


@dataclass(frozen=True)
class AddOutcome:
    kind: AddKind
    code: str | None = None
    parcel: Parcel | None = None
    result: TrackingResult | None = None
    error: CarrierError | None = None
    candidates: tuple[CarrierCode, ...] = ()
    link_carriers: tuple[CarrierCode, ...] = ()


class ParcelService:
    def __init__(
        self,
        repo: Repository,
        carriers: Mapping[CarrierCode, Carrier],
        http: httpx.AsyncClient,
        settings: Settings,
        now: Callable[[], datetime],
    ) -> None:
        self._repo = repo
        self._carriers = carriers
        self._http = http
        self._settings = settings
        self._now = now

    async def add(
        self,
        user: User,
        raw_code: str,
        phone_last4: str | None = None,
        carrier: CarrierCode | None = None,
    ) -> AddOutcome:
        code = normalize_code(raw_code)
        if carrier is not None:
            if not GENERIC_CODE_RE.match(code):
                return AddOutcome("invalid_code", code=code or None)
            candidates = [carrier]
        else:
            candidates = detect_carriers(code)

        tracked = [c for c in candidates if is_tracked(c) and c in self._carriers]
        link_only = tuple(c for c in candidates if not is_tracked(c))
        if not tracked and not link_only:
            return AddOutcome("invalid_code", code=code or None)
        if phone_last4 is not None and not is_valid_last4(phone_last4):
            return AddOutcome("invalid_phone", code=code)

        uid = user.telegram_id
        if not tracked:
            log.info(
                "link-only code user=%s carriers=%s code=%s",
                uid,
                ",".join(link_only),
                mask_code(code),
            )
            return AddOutcome("link_only", code=code, link_carriers=link_only)
        if await self._repo.find_parcel(uid, code) is not None:
            return AddOutcome("duplicate", code=code)
        if await self._repo.count_active_parcels(uid) >= self._settings.max_parcels_per_user:
            return AddOutcome("limit", code=code)

        last4 = phone_last4 or user.default_phone_last4
        tryable = [c for c in tracked if not needs_phone(c) or last4]
        phone_missing = tuple(c for c in tracked if needs_phone(c) and not last4)

        attempts = await self._try_candidates(code, tryable, last4)
        try:
            if attempts:
                winner, outcome = attempts[-1]
                if isinstance(outcome, TrackingResult) and outcome.found:
                    return await self._store_found(uid, code, winner, outcome, last4)
            if phone_missing:
                return AddOutcome("needs_phone", code=code, candidates=phone_missing)
            return await self._store_pending(uid, code, tracked, attempts, last4, link_only)
        except DuplicateParcelError:
            return AddOutcome("duplicate", code=code)

    async def _try_candidates(
        self, code: str, tryable: Sequence[CarrierCode], last4: str | None
    ) -> list[Attempt]:
        attempts: list[Attempt] = []
        for candidate in tryable:
            digits = last4 if needs_phone(candidate) else None
            try:
                result = await self._carriers[candidate].fetch(self._http, code, digits)
            except CarrierError as err:
                attempts.append((candidate, err))
                continue
            attempts.append((candidate, result))
            if result.found:
                break
        return attempts

    async def _store_found(
        self,
        uid: int,
        code: str,
        carrier: CarrierCode,
        result: TrackingResult,
        last4: str | None,
    ) -> AddOutcome:
        now = self._now()
        interval = self._settings.poll_interval
        parcel = await self._repo.add_parcel(
            user_id=uid,
            carrier=carrier,
            candidates=(carrier,),
            tracking_number=code,
            phone_last4=last4 if needs_phone(carrier) else None,
            now=now,
            next_check_at=now + interval,
        )
        await self._repo.insert_events(parcel.id, result.events, now)
        state = "delivered" if result.delivered else "returned" if result.returned else "in_transit"
        latest = result.latest
        await self._repo.record_check_success(
            parcel.id,
            state=state,
            last_status_text=latest.description if latest else None,
            last_event_at=latest.time if latest else None,
            next_check_at=now + interval,
            now=now,
            delivered_at=latest.time if state == "delivered" and latest else None,
        )
        log.info(
            "parcel added user=%s carrier=%s code=%s state=%s", uid, carrier, mask_code(code), state
        )
        return AddOutcome(
            "added", code=code, parcel=await self._repo.get_parcel(parcel.id), result=result
        )

    async def _store_pending(
        self,
        uid: int,
        code: str,
        tracked: Sequence[CarrierCode],
        attempts: Sequence[Attempt],
        last4: str | None,
        link_only: tuple[CarrierCode, ...],
    ) -> AddOutcome:
        now = self._now()
        interval = self._settings.poll_interval
        parcel = await self._repo.add_parcel(
            user_id=uid,
            carrier=tracked[0] if len(tracked) == 1 else None,
            candidates=tuple(tracked),
            tracking_number=code,
            phone_last4=last4 if any(needs_phone(c) for c in tracked) else None,
            now=now,
            next_check_at=now + interval,
        )
        errors = [outcome for _, outcome in attempts if isinstance(outcome, CarrierError)]
        if attempts and len(errors) == len(attempts):
            failures = parcel.consecutive_failures + 1
            await self._repo.record_check_failure(
                parcel.id, next_check_at=now + min(interval * 2**failures, MAX_BACKOFF), now=now
            )
            log.info(
                "parcel added user=%s carrier=%s code=%s state=pending error=%s",
                uid,
                parcel.carrier or "auto",
                mask_code(code),
                errors[-1].reason,
            )
            return AddOutcome(
                "added",
                code=code,
                parcel=await self._repo.get_parcel(parcel.id),
                error=errors[-1],
                link_carriers=link_only,
            )
        not_found = next((o for _, o in reversed(attempts) if isinstance(o, TrackingResult)), None)
        await self._repo.record_check_success(
            parcel.id,
            state="pending",
            last_status_text=None,
            last_event_at=None,
            next_check_at=now + interval,
            now=now,
        )
        log.info(
            "parcel added user=%s carrier=%s code=%s state=pending",
            uid,
            parcel.carrier or "auto",
            mask_code(code),
        )
        return AddOutcome(
            "added",
            code=code,
            parcel=await self._repo.get_parcel(parcel.id),
            result=not_found,
            link_carriers=link_only,
        )

    async def list_for(self, user_id: int) -> list[Parcel]:
        return await self._repo.list_parcels(
            user_id, terminal_since=self._now() - DELIVERED_VISIBLE_FOR
        )

    async def resolve(self, user_id: int, ref: str) -> Parcel | None:
        ref = ref.strip()
        if _INDEX_REF.fullmatch(ref):
            parcels = await self.list_for(user_id)
            index = int(ref)
            return parcels[index - 1] if 1 <= index <= len(parcels) else None
        return await self._repo.find_parcel(user_id, normalize_code(ref))

    async def remove(self, user_id: int, ref: str) -> Parcel | None:
        parcel = await self.resolve(user_id, ref)
        if parcel is None:
            return None
        await self._repo.delete_parcel(parcel.id)
        log.info("parcel removed user=%s code=%s", user_id, mask_code(parcel.tracking_number))
        return parcel

    async def rename(self, user_id: int, ref: str, label: str | None) -> Parcel | None:
        parcel = await self.resolve(user_id, ref)
        if parcel is None:
            return None
        cleaned = label.strip()[:MAX_LABEL_LENGTH] if label and label.strip() else None
        await self._repo.set_label(parcel.id, cleaned, self._now())
        return await self._repo.get_parcel(parcel.id)

    async def history(self, user_id: int, ref: str) -> tuple[Parcel, list[TrackingEvent]] | None:
        parcel = await self.resolve(user_id, ref)
        if parcel is None:
            return None
        return parcel, await self._repo.list_events(parcel.id, MAX_EVENTS_IN_HISTORY)

    async def set_default_phone(self, user_id: int, last4: str | None) -> None:
        if last4 is not None and not is_valid_last4(last4):
            raise ValueError("default phone digits must be exactly 4 digits")
        await self._repo.set_default_phone(user_id, last4)
