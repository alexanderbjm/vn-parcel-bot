from pathlib import Path

import pytest
from PIL import Image

from tests.fakes import FakeNotifier
from vn_parcel_bot import texts
from vn_parcel_bot.constants import OUT_FOR_DELIVERY_PROGRESS
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.stickers import (
    ICON_DIR,
    MANUAL_KEY,
    SHIPPED_KEY,
    STICKER_STATUSES,
    icon_statuses,
    register_icons,
    sticker_for,
    sticker_status,
)

ADMIN = 111
# Telegram refuses a sticker over 512 KB and shows one at its largest on a 512 px side.
STICKER_MAX_BYTES = 512 * 1024


@pytest.fixture
async def repo():
    opened = await Repository.open(":memory:")
    yield opened
    await opened.close()


def test_every_shipped_sticker_is_a_telegram_sticker():
    assert icon_statuses() == STICKER_STATUSES
    for status in STICKER_STATUSES:
        path = Path(ICON_DIR) / f"{status}.webp"
        assert path.stat().st_size <= STICKER_MAX_BYTES, status
        with Image.open(path) as icon:
            assert icon.format == "WEBP"
            assert icon.size == (512, 512)
            assert icon.mode == "RGBA"
            # A sticker with no transparency sits on the chat as a white square.
            assert icon.getchannel("A").getextrema()[0] == 0, status


def test_every_status_has_a_vietnamese_label():
    assert set(texts.STICKER_STATUS_TEXT) == set(STICKER_STATUSES)


@pytest.mark.parametrize(
    ("state", "progress", "expected"),
    [
        ("in_transit", 50, "moving"),
        ("in_transit", None, "moving"),
        ("in_transit", OUT_FOR_DELIVERY_PROGRESS - 1, "moving"),
        ("in_transit", OUT_FOR_DELIVERY_PROGRESS, "near"),
        ("delivered", 100, "delivered"),
        ("returned", 40, "returned"),
    ],
)
def test_sticker_status_follows_the_delivery(state, progress, expected):
    assert sticker_status(state, progress) == expected


def test_sticker_status_can_never_send_a_status_without_a_sticker():
    # Every state a parcel can hold must land on something that ships a .webp.
    for state in ("pending", "in_transit", "delivered", "returned", "expired", "stale"):
        for progress in (None, 0, 50, 100):
            assert sticker_status(state, progress) in STICKER_STATUSES


async def test_register_uploads_each_sticker_once(repo):
    notifier = FakeNotifier()
    assert await register_icons(repo, notifier, ADMIN) == 4
    assert [chat_id for chat_id, _ in notifier.uploads] == [ADMIN] * 4
    assert len(notifier.uploads) == 4
    for status in STICKER_STATUSES:
        assert await repo.get_meta(f"{SHIPPED_KEY}{status}") == "file-uploaded"
    assert await register_icons(repo, notifier, ADMIN) == 0
    assert len(notifier.uploads) == 4


async def test_register_skips_a_failed_upload(repo):
    notifier = FakeNotifier()
    notifier.upload_file_id = None
    assert await register_icons(repo, notifier, ADMIN) == 0
    assert await repo.get_meta(f"{SHIPPED_KEY}moving") is None

    notifier.upload_file_id = "file-uploaded"
    assert await register_icons(repo, notifier, ADMIN) == 4


async def test_register_survives_a_raising_notifier(repo):
    class Broken(FakeNotifier):
        async def upload_sticker(self, chat_id: int, image: bytes) -> str | None:
            raise RuntimeError("telegram said no")

    assert await register_icons(repo, Broken(), ADMIN) == 0


async def test_the_manual_sticker_wins_over_the_shipped_one(repo):
    await repo.set_meta(f"{SHIPPED_KEY}moving", "file-shipped")
    assert await sticker_for(repo, "moving") == "file-shipped"
    await repo.set_meta(f"{MANUAL_KEY}moving", "file-manual")
    assert await sticker_for(repo, "moving") == "file-manual"
    assert await sticker_for(repo, "delivered") is None
