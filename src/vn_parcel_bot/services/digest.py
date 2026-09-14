import logging
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from vn_parcel_bot.config import Settings
from vn_parcel_bot.constants import FIRST_DIGEST_WINDOW
from vn_parcel_bot.db.repo import Parcel, Repository
from vn_parcel_bot.keyboards import list_keyboard
from vn_parcel_bot.services.formatting import format_digest

log = logging.getLogger(__name__)

DIGEST_META_PREFIX = "digest:last:"


class DigestNotifier(Protocol):
    async def send(
        self, chat_id: int, text: str, *, silent: bool = False, reply_markup: object = None
    ) -> None: ...


class DigestService:
    def __init__(
        self,
        repo: Repository,
        notifier: DigestNotifier,
        settings: Settings,
        now: Callable[[], datetime],
    ) -> None:
        self._repo = repo
        self._notifier = notifier
        self._settings = settings
        self._now = now

    async def _compose(self, user_id: int, cutoff: datetime) -> tuple[str, list[Parcel]] | None:
        stored = await self._repo.get_meta(f"{DIGEST_META_PREFIX}{user_id}")
        since = datetime.fromisoformat(stored) if stored else cutoff - FIRST_DIGEST_WINDOW
        parcels = await self._repo.list_parcels(user_id, terminal_since=since)
        if not parcels:
            return None
        changed = await self._repo.parcel_ids_with_events_since(user_id, since)
        return format_digest(parcels, changed, cutoff, self._settings.tz), parcels

    async def build(self, user_id: int, cutoff: datetime) -> str | None:
        composed = await self._compose(user_id, cutoff)
        return None if composed is None else composed[0]

    async def send_all(self) -> int:
        cutoff = self._now()
        sent = 0
        for user in await self._repo.list_users():
            if not user.is_allowed:
                continue
            composed = await self._compose(user.telegram_id, cutoff)
            if composed is None:
                continue
            text, parcels = composed
            keyboard = list_keyboard(list(enumerate(parcels, start=1)), page=1, pages=1)
            try:
                await self._notifier.send(
                    user.telegram_id, text, silent=False, reply_markup=keyboard
                )
            except Exception:
                log.warning("digest send failed user=%s", user.telegram_id, exc_info=True)
                continue
            await self._repo.set_meta(f"{DIGEST_META_PREFIX}{user.telegram_id}", cutoff.isoformat())
            sent += 1
        log.info("digest run sent=%s", sent)
        return sent
