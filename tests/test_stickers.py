import io
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from tests.fakes import FakeNotifier
from vn_parcel_bot import texts
from vn_parcel_bot.constants import OUT_FOR_DELIVERY_PROGRESS
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services import stickers
from vn_parcel_bot.services.stickers import (
    ART_KEY,
    COVER_KEY,
    ICON_DIR,
    MANUAL_KEY,
    SHIPPED_KEY,
    STICKER_STATUSES,
    cover_path,
    icon_statuses,
    parcel_sticker,
    register_icons,
    save_cover,
    sticker_for,
    sticker_status,
    sweep_covers,
)

ADMIN = 111
T0 = datetime(2026, 9, 1, 1, 0, tzinfo=UTC)
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


async def test_a_redrawn_sticker_is_uploaded_again(repo, tmp_path, monkeypatch):
    """The cached file_id is the upload of a particular drawing, not a permanent answer."""
    for status in STICKER_STATUSES:
        (tmp_path / f"{status}.webp").write_bytes((ICON_DIR / f"{status}.webp").read_bytes())
    monkeypatch.setattr(stickers, "ICON_DIR", tmp_path)
    notifier = FakeNotifier()

    assert await register_icons(repo, notifier, ADMIN) == 4
    assert await register_icons(repo, notifier, ADMIN) == 0, "the same drawing is not re-sent"

    # Any change to the file is a new drawing — the fake notifier never reads it.
    (tmp_path / "moving.webp").write_bytes((ICON_DIR / "moving.webp").read_bytes() + b"redrawn")
    assert await register_icons(repo, notifier, ADMIN) == 1
    assert await repo.get_meta(f"{SHIPPED_KEY}moving") == "file-uploaded"
    assert await repo.get_meta(f"{ART_KEY}moving") is not None


def photo(colour: tuple[int, int, int] = (200, 120, 60)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (800, 600), colour).save(buffer, "PNG")
    return buffer.getvalue()


async def test_a_parcel_cover_is_kept_as_a_square_sticker(repo, tmp_path):
    directory = tmp_path / "covers"

    assert save_cover(directory, 7, photo()) is True

    with Image.open(cover_path(directory, 7)) as cover:
        assert cover.size == (512, 512)
        assert cover.format == "WEBP"


async def test_a_cover_that_cannot_be_read_is_simply_not_kept(tmp_path):
    assert save_cover(tmp_path / "covers", 7, b"not an image") is False
    assert not (tmp_path / "covers" / "7.webp").exists()


async def test_a_parcel_without_a_cover_sends_the_shipped_sticker(repo, tmp_path):
    notifier = FakeNotifier()

    assert await parcel_sticker(repo, notifier, ADMIN, tmp_path, 7, "moving") is None
    assert notifier.uploads == []


async def test_a_parcel_cover_is_uploaded_once_per_status(repo, tmp_path):
    directory = tmp_path / "covers"
    save_cover(directory, 7, photo())
    notifier = FakeNotifier()

    assert await parcel_sticker(repo, notifier, ADMIN, directory, 7, "moving") == "file-uploaded"
    assert await parcel_sticker(repo, notifier, ADMIN, directory, 7, "moving") == "file-uploaded"
    assert len(notifier.uploads) == 1, "the same cover and status are not drawn twice"

    await parcel_sticker(repo, notifier, ADMIN, directory, 7, "near")
    assert len(notifier.uploads) == 2, "a different status is a different sticker"


async def test_a_redrawn_cover_makes_a_new_parcel_sticker(repo, tmp_path):
    directory = tmp_path / "covers"
    save_cover(directory, 7, photo())
    notifier = FakeNotifier()
    await parcel_sticker(repo, notifier, ADMIN, directory, 7, "moving")

    save_cover(directory, 7, photo((10, 200, 30)))
    await parcel_sticker(repo, notifier, ADMIN, directory, 7, "moving")

    assert len(notifier.uploads) == 2


async def test_an_upload_that_fails_leaves_the_parcel_on_the_shipped_sticker(repo, tmp_path):
    directory = tmp_path / "covers"
    save_cover(directory, 7, photo())
    notifier = FakeNotifier()
    notifier.upload_file_id = None

    assert await parcel_sticker(repo, notifier, ADMIN, directory, 7, "moving") is None
    assert await repo.get_meta(f"{COVER_KEY}7:moving") is None


async def test_the_sweep_drops_covers_of_parcels_that_are_gone(repo, tmp_path):
    await repo.upsert_user(1, now=T0, is_allowed=True)
    parcel = await repo.add_parcel(
        user_id=1,
        carrier="spx",
        candidates=("spx",),
        tracking_number="SPXVN000000000001",
        phone_last4=None,
        now=T0,
        next_check_at=T0,
    )
    directory = tmp_path / "covers"
    save_cover(directory, parcel.id, photo())
    save_cover(directory, 999, photo())
    await repo.set_meta(f"{COVER_KEY}999:moving", "file-cover")
    await repo.set_meta(f"{ART_KEY}{COVER_KEY}999:moving", "hash")

    assert await sweep_covers(repo, directory) == 1

    assert cover_path(directory, parcel.id).exists()
    assert not cover_path(directory, 999).exists()
    assert await repo.get_meta(f"{COVER_KEY}999:moving") is None
    assert await repo.get_meta(f"{ART_KEY}{COVER_KEY}999:moving") is None


async def test_the_sweep_leaves_an_absent_directory_alone(repo, tmp_path):
    assert await sweep_covers(repo, tmp_path / "missing") == 0
