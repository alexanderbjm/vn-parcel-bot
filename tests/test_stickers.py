from pathlib import Path

import pytest
from PIL import Image

from tests.fakes import FakeNotifier
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.stickers import (
    ICON_DIR,
    MANUAL_KEY,
    SEEDED_KEY,
    SHIPPED_KEY,
    icon_carriers,
    register_icons,
    sticker_for,
)

ADMIN = 111
# Telegram refuses a sticker over 512 KB and shows one at its largest on a 512 px side.
STICKER_MAX_BYTES = 512 * 1024


@pytest.fixture
async def repo():
    opened = await Repository.open(":memory:")
    yield opened
    await opened.close()


def test_every_shipped_icon_is_a_telegram_sticker():
    assert icon_carriers() == ("cainiao", "ghn", "jt", "ninjavan", "spx")
    for carrier in icon_carriers():
        path = Path(ICON_DIR) / f"{carrier}.webp"
        assert path.stat().st_size <= STICKER_MAX_BYTES, carrier
        with Image.open(path) as icon:
            assert icon.format == "WEBP"
            assert icon.size == (512, 512)
            assert icon.mode == "RGBA"
            # A sticker with no transparency sits on the chat as a white square.
            assert icon.getchannel("A").getextrema()[0] == 0, carrier


async def test_register_uploads_each_icon_once(repo):
    notifier = FakeNotifier()
    assert await register_icons(repo, notifier, ADMIN) == 5
    assert [chat_id for chat_id, _ in notifier.uploads] == [ADMIN] * 5
    assert len(notifier.uploads) == 5
    for carrier in icon_carriers():
        assert await repo.get_meta(f"{SHIPPED_KEY}{carrier}") == "file-uploaded"
    assert await register_icons(repo, notifier, ADMIN) == 0
    assert len(notifier.uploads) == 5


async def test_register_skips_a_failed_upload(repo):
    notifier = FakeNotifier()
    notifier.upload_file_id = None
    assert await register_icons(repo, notifier, ADMIN) == 0
    assert await repo.get_meta(f"{SHIPPED_KEY}spx") is None

    notifier.upload_file_id = "file-uploaded"
    assert await register_icons(repo, notifier, ADMIN) == 5


async def test_register_survives_a_raising_notifier(repo):
    class Broken(FakeNotifier):
        async def upload_sticker(self, chat_id: int, image: bytes) -> str | None:
            raise RuntimeError("telegram said no")

    assert await register_icons(repo, Broken(), ADMIN) == 0


async def test_the_manual_sticker_wins_over_the_shipped_icon(repo):
    await repo.set_meta(f"{SHIPPED_KEY}spx", "file-shipped")
    assert await sticker_for(repo, "spx") == "file-shipped"
    await repo.set_meta(f"{MANUAL_KEY}spx", "file-manual")
    assert await sticker_for(repo, "spx") == "file-manual"
    assert await sticker_for(repo, "fourpx") is None


async def test_a_sticker_mapped_before_the_icons_is_replaced_once(repo):
    await repo.set_meta(f"{MANUAL_KEY}spx", "file-from-a-pack")
    notifier = FakeNotifier()
    await register_icons(repo, notifier, ADMIN)
    assert await repo.get_meta(f"{MANUAL_KEY}spx") is None
    assert await repo.get_meta(SEEDED_KEY) == "1"

    # A sticker the admin maps afterwards is theirs, and the next start leaves it alone.
    await repo.set_meta(f"{MANUAL_KEY}spx", "file-manual")
    await register_icons(repo, notifier, ADMIN)
    assert await repo.get_meta(f"{MANUAL_KEY}spx") == "file-manual"
