import io

import pytest
from PIL import Image, ImageChops, UnidentifiedImageError

from vn_parcel_bot import texts
from vn_parcel_bot.services.sticker_art import (
    BAND_FOOT,
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
    band_bottom = SIZE - BAND_FOOT
    assert cover.getpixel((SIZE // 2, band_bottom - 10))[:3] == COLOURS[status], status
    assert cover.getpixel((SIZE // 2, 8))[:3] != COLOURS[status], "the photo is still visible"


@pytest.mark.parametrize("status", STICKER_STATUSES)
def test_a_cover_keeps_its_words_out_of_the_timestamp_corner(status):
    # A chat draws its message time over the bottom-right of a sticker. The band used to reach the
    # foot, so the time landed on the words and hid them; the test photo is a flat colour and the
    # words are the only white in the picture, so where the white ends says where the words end.
    with Image.open(io.BytesIO(sticker_bytes(photo(), status))) as opened:
        red, green, blue = opened.convert("RGB").split()
    words = ImageChops.multiply(ImageChops.multiply(red, green), blue).point(
        lambda value: 255 if value > 250 else 0
    )
    box = words.getbbox()
    assert box, "the status words are missing"
    assert box[3] <= SIZE - BAND_FOOT, "the words reach the corner the time sits in"


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
