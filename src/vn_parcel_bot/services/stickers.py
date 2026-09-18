"""The delivery-status stickers sent just before an update.

A bot cannot create a sticker pack, but it can upload a .webp and have Telegram send it as a
sticker on its own, so the four drawn in ``assets/status`` need nothing installed by hand: each
is uploaded once, the file_id that comes back is cached in ``meta``, and every later send
reuses it. A sticker the admin mapped with /sticker always wins over a shipped one.

They key on the parcel's *status*, not on its carrier: a parcel keeps its carrier for life, so a
carrier sticker says nothing about the thing that just happened, while the status is exactly
that — on the way, nearly there, delivered, coming back.
"""

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Protocol

from vn_parcel_bot.constants import OUT_FOR_DELIVERY_PROGRESS
from vn_parcel_bot.services.sticker_art import cover_bytes, sticker_bytes

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
# A parcel's own cover, and the sticker made from it for one status.
COVER_DIR_NAME = "covers"
COVER_KEY = "sticker-cover:"


def covers_dir(db_path: Path) -> Path:
    """Where a parcel's own picture is kept: beside the database, which is gitignored."""
    return Path(db_path).parent / COVER_DIR_NAME


def cover_path(directory: Path, parcel_id: int) -> Path:
    return Path(directory) / f"{parcel_id}.webp"


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
    async def get_parcel(self, parcel_id: int) -> object | None: ...


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


def save_cover(directory: Path, parcel_id: int, image_bytes: bytes) -> bool:
    """Keep the picture a parcel was added from, for its own stickers.

    False when the picture cannot be read or written — a parcel simply keeps the shipped
    stickers then, which is never a reason to fail the add.
    """
    try:
        image = cover_bytes(image_bytes)
    except Exception:
        log.warning("cover unreadable parcel=%s", parcel_id, exc_info=True)
        return False
    try:
        Path(directory).mkdir(parents=True, exist_ok=True)
        cover_path(directory, parcel_id).write_bytes(image)
    except OSError:
        log.warning("cover not writable parcel=%s", parcel_id, exc_info=True)
        return False
    return True


async def parcel_sticker(
    repo: StickerRepo,
    notifier: StickerNotifier,
    admin_id: int,
    directory: Path,
    parcel_id: int,
    status: str,
) -> str | None:
    """The parcel's own cover with the status written on it, or None when it has no cover.

    The upload is cached like a shipped sticker's, but keyed by the cover as well as the
    status, so redrawing a cover — or a status gaining new words — makes a new sticker.
    """
    path = cover_path(directory, parcel_id)
    if not path.exists():
        return None
    try:
        cover = path.read_bytes()
    except OSError:
        log.warning("cover unreadable parcel=%s", parcel_id, exc_info=True)
        return None
    digest = hashlib.sha256(status.encode("utf-8") + cover).hexdigest()
    key = f"{COVER_KEY}{parcel_id}:{status}"
    if await repo.get_meta(f"{ART_KEY}{key}") == digest:
        return await repo.get_meta(key)
    try:
        image = sticker_bytes(cover, status)
        file_id = await notifier.upload_sticker(admin_id, image)
    except Exception:
        log.warning("parcel sticker upload raised parcel=%s status=%s", parcel_id, status)
        return None
    if not file_id:
        log.warning("parcel sticker upload failed parcel=%s status=%s", parcel_id, status)
        return None
    await repo.set_meta(key, file_id)
    await repo.set_meta(f"{ART_KEY}{key}", digest)
    return file_id


def cover_paths(directory: Path) -> list[Path]:
    """The cover files on disk, sorted; empty when nothing has been kept yet."""
    if not Path(directory).exists():
        return []
    return sorted(Path(directory).glob("*.webp"))


async def sweep_covers(repo: StickerRepo, directory: Path) -> int:
    """Forget the cover and the cached stickers of parcels that no longer exist.

    A parcel leaves by being removed or by being purged 30 days after it finished, and neither
    knows about a file on disk, so the startup sweep is what keeps `covers/` from growing for
    ever. Returns how many covers were dropped.
    """
    paths = await asyncio.to_thread(cover_paths, directory)
    dropped = 0
    for path in paths:
        try:
            parcel_id = int(path.stem)
        except ValueError:
            continue
        if await repo.get_parcel(parcel_id) is not None:
            continue
        path.unlink(missing_ok=True)
        for status in STICKER_STATUSES:
            key = f"{COVER_KEY}{parcel_id}:{status}"
            await repo.delete_meta(key)
            await repo.delete_meta(f"{ART_KEY}{key}")
        dropped += 1
    if dropped:
        log.info("covers dropped count=%s", dropped)
    return dropped
