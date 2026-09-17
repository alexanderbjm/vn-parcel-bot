"""The carrier icons sent just before an update.

A bot cannot create a sticker pack, but it can upload a .webp and have Telegram send it as a
sticker on its own, so the logos shipped in ``assets/carriers`` need nothing installed by
hand: each is uploaded once, the file_id that comes back is cached in ``meta``, and every
later send reuses it. A sticker the admin mapped with /sticker always wins over a shipped one.
"""

import logging
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "carriers"

# The admin's own sticker for a carrier, and the shipped icon behind it.
MANUAL_KEY = "sticker:"
SHIPPED_KEY = "sticker-auto:"
# Written once, after the shipped icons replace the stickers mapped before they existed.
SEEDED_KEY = "stickers:shipped-icons"


class StickerRepo(Protocol):
    async def get_meta(self, key: str) -> str | None: ...
    async def set_meta(self, key: str, value: str) -> None: ...
    async def delete_meta(self, key: str) -> None: ...


class StickerNotifier(Protocol):
    async def upload_sticker(self, chat_id: int, image: bytes) -> str | None: ...


def icon_carriers() -> tuple[str, ...]:
    """Every carrier with a shipped icon."""
    return tuple(sorted(path.stem for path in ICON_DIR.glob("*.webp")))


async def sticker_for(repo: StickerRepo, carrier: str) -> str | None:
    """What to send for a carrier: the admin's sticker, else the shipped icon, else nothing."""
    manual = await repo.get_meta(f"{MANUAL_KEY}{carrier}")
    if manual:
        return manual
    return await repo.get_meta(f"{SHIPPED_KEY}{carrier}")


async def register_icons(repo: StickerRepo, notifier: StickerNotifier, admin_id: int) -> int:
    """Upload every shipped icon Telegram has not been given yet; return how many were added.

    A sticker that belongs to no pack has no file_id until it has been sent once, so the first
    send goes to the admin's own chat and is deleted right away. A failure is logged and
    skipped: a missing icon must never be a reason for the bot not to start.
    """
    if await repo.get_meta(SEEDED_KEY) is None:
        await _drop_stickers_mapped_before_icons(repo)
        await repo.set_meta(SEEDED_KEY, "1")
    uploaded = 0
    for carrier in icon_carriers():
        key = f"{SHIPPED_KEY}{carrier}"
        if await repo.get_meta(key):
            continue
        image = (ICON_DIR / f"{carrier}.webp").read_bytes()
        try:
            file_id = await notifier.upload_sticker(admin_id, image)
        except Exception:
            log.warning("carrier icon upload raised carrier=%s", carrier, exc_info=True)
            continue
        if not file_id:
            log.warning("carrier icon upload failed carrier=%s", carrier)
            continue
        await repo.set_meta(key, file_id)
        uploaded += 1
    if uploaded:
        log.info("carrier icons uploaded count=%s", uploaded)
    return uploaded


async def _drop_stickers_mapped_before_icons(repo: StickerRepo) -> None:
    """Let a shipped icon take over from the sticker mapped for that carrier earlier."""
    for carrier in icon_carriers():
        if await repo.get_meta(f"{MANUAL_KEY}{carrier}") is not None:
            await repo.delete_meta(f"{MANUAL_KEY}{carrier}")
            log.info("shipped icon replaced the sticker mapped earlier carrier=%s", carrier)
