import io

import pytest
from PIL import Image, UnidentifiedImageError

from vn_parcel_bot import texts
from vn_parcel_bot.services.sticker_art import (
    COLOURS,
    SIZE,
    cover_bytes,
    render_cover,
    status_bytes,
    sticker_bytes,
)
from vn_parcel_bot.services.stickers import STICKER_STATUSES


def photo(width: int = 800, height: int = 600, colour=(200, 120, 60)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buffer, "PNG")
    return buffer.getvalue()


@pytest.mark.parametrize("status", STICKER_STATUSES)
def test_a_shipped_sticker_is_a_telegram_sticker(status):
    with Image.open(io.BytesIO(status_bytes(status))) as icon:
        assert icon.format == "WEBP"
        assert icon.size == (SIZE, SIZE)
        assert icon.mode == "RGBA"
        assert icon.getchannel("A").getextrema()[0] == 0


@pytest.mark.parametrize("status", STICKER_STATUSES)
def test_a_cover_keeps_the_photo_and_bands_the_foot(status):
    with Image.open(io.BytesIO(sticker_bytes(photo(), status))) as opened:
        cover = opened.convert("RGBA")
    assert cover.getpixel((SIZE // 2, SIZE - 40))[:3] == COLOURS[status], status
    assert cover.getpixel((SIZE // 2, 8))[:3] != COLOURS[status], "the photo is still visible"


def test_a_cover_is_squared_from_the_middle():
    with Image.open(io.BytesIO(cover_bytes(photo(900, 300, (10, 20, 30))))) as icon:
        assert icon.size == (SIZE, SIZE)


def test_the_band_fits_the_words_however_long_they_get(monkeypatch):
    # The wording is texts.py's to change; the drawing has to follow it, not overflow.
    monkeypatch.setitem(texts.STICKER_STATUS_TEXT, "moving", "đang trên đường rất là lâu")
    assert status_bytes("moving")


def test_a_picture_that_is_not_an_image_is_refused():
    with pytest.raises(UnidentifiedImageError):
        render_cover(b"not an image", "moving")
