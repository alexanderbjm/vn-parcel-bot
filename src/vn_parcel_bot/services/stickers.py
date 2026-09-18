"""The delivery-status stickers sent just before an update.

A bot cannot create a sticker pack, but it can upload a .webp and have Telegram send it as a
sticker on its own, so the four drawn in ``assets/status`` need nothing installed by hand: each
is uploaded once, the file_id that comes back is cached in ``meta``, and every later send
reuses it. A sticker the admin mapped with /sticker always wins over a shipped one.

They key on the parcel's *status*, not on its carrier: a parcel keeps its carrier for life, so a
carrier sticker says nothing about the thing that just happened, while the status is exactly
that — on the way, nearly there, delivered, coming back.
"""

import hashlib
import logging
from pathlib import Path
from typing import Protocol

from vn_parcel_bot.constants import OUT_FOR_DELIVERY_PROGRESS

log = logging.getLogger(__name__)

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "status"

# The vocabulary, in the order a parcel passes through it. ``icon_statuses`` ships exactly
# these, and anything not listed here is not a status the bot can talk about.
STICKER_STATUSES = ("moving", "near", "delivered", "returned")

# The admin's own sticker for a status, the shipped one behind it, and the drawing that sticker
# was uploaded from.
MANUAL_KEY = "sticker:"
SHIPPED_KEY = "sticker-auto:"
ART_KEY = "sticker-art:"


def sticker_status(state: str, progress: int | None) -> str:
    """Which of ``STICKER_STATUSES`` a parcel state calls for.

    Only ever asked about a parcel with something new to say, so the state is in transit,
    delivered or returned by construction; anything else reads as on the way, which is what an
    update means.
    """
    if state == "delivered":
        return "delivered"
    if state == "returned":
        return "returned"
    if state == "in_transit" and progress is not None and progress >= OUT_FOR_DELIVERY_PROGRESS:
        return "near"
    return "moving"


class StickerRepo(Protocol):
    async def get_meta(self, key: str) -> str | None: ...
    async def set_meta(self, key: str, value: str) -> None: ...
    async def delete_meta(self, key: str) -> None: ...


class StickerNotifier(Protocol):
    async def upload_sticker(self, chat_id: int, image: bytes) -> str | None: ...


def icon_statuses() -> tuple[str, ...]:
    """Every status with a shipped sticker, in the order of the vocabulary."""
    shipped = {path.stem for path in ICON_DIR.glob("*.webp")}
    return tuple(status for status in STICKER_STATUSES if status in shipped)


async def sticker_for(repo: StickerRepo, status: str) -> str | None:
    """What to send for a status: the admin's sticker, else the shipped one, else nothing."""
    manual = await repo.get_meta(f"{MANUAL_KEY}{status}")
    if manual:
        return manual
    return await repo.get_meta(f"{SHIPPED_KEY}{status}")


async def register_icons(repo: StickerRepo, notifier: StickerNotifier, admin_id: int) -> int:
    """Upload every shipped sticker Telegram does not have the current drawing of; return how many.

    A sticker that belongs to no pack has no file_id until it has been sent once, so the first
    send goes to the admin's own chat and is deleted right away. A failure is logged and
    skipped: a missing sticker must never be a reason for the bot not to start.

    The uploaded drawing is remembered by its hash, not merely by having been uploaded once: a
    `file_id` would otherwise keep the bot sending a picture nobody has drawn for months, which
    is exactly what happened when the carrier logos became status stickers.
    """
    uploaded = 0
    for status in icon_statuses():
        image = (ICON_DIR / f"{status}.webp").read_bytes()
        digest = hashlib.sha256(image).hexdigest()
        if await repo.get_meta(f"{ART_KEY}{status}") == digest:
            continue
        try:
            file_id = await notifier.upload_sticker(admin_id, image)
        except Exception:
            log.warning("status sticker upload raised status=%s", status, exc_info=True)
            continue
        if not file_id:
            log.warning("status sticker upload failed status=%s", status)
            continue
        await repo.set_meta(f"{SHIPPED_KEY}{status}", file_id)
        await repo.set_meta(f"{ART_KEY}{status}", digest)
        uploaded += 1
    if uploaded:
        log.info("status stickers uploaded count=%s", uploaded)
    return uploaded
