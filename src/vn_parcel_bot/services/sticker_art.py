"""Drawing a status onto a sticker: the shipped art, and a cover the admin supplies.

One place draws the words, so a shipped sticker and a custom cover can never disagree about
what a status looks like. ``render_status`` makes the art that ships (a coloured badge), and
``stamp_cover`` writes the same words onto a photo, which is how a parcel's own screenshot or an
image the admin sent to ``/sticker`` becomes a sticker carrying the status.

Everything is drawn at ``SCALE`` times the final size and shrunk with LANCZOS: PIL has no
antialiasing, and a circle drawn at 512 px alone shows a stepped edge. Only a system font is
read and only its rendered output is ever sent or committed, so the art carries no licensed
glyph.
"""

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from vn_parcel_bot import texts

SIZE = 512
SCALE = 4
CANVAS = SIZE * SCALE
WHITE = (255, 255, 255, 255)

# One colour per status: blue on the way, orange nearly there, green delivered, red back.
COLOURS = {
    "moving": (47, 107, 255),
    "near": (255, 138, 0),
    "delivered": (34, 180, 90),
    "returned": (229, 72, 77),
}
# Vietnamese needs a font that carries the diacritics. Both of these are on a stock Windows PC.
FONT_CANDIDATES = (
    Path(r"C:\Windows\Fonts\segoeuib.ttf"),
    Path(r"C:\Windows\Fonts\arialbd.ttf"),
)
MAX_FONT_SIZE = 120
# Room for the text inside the badge, in final 512 px coordinates.
TEXT_WIDTH = 372
TEXT_HEIGHT = 300
LINE_SPACING = 1.14
# One line reads better than two, but only while it stays big: "SẮP GIAO" fits on one line at
# ~75 px, while "ĐANG TRÊN ĐƯỜNG" would drop to ~48 px to do so, and two lines give it ~90.
SINGLE_LINE_MIN_SIZE = 64
# The band a cover gets along its foot, so the photo above stays visible.
BAND_MARGIN = 18
BAND_HEIGHT = 132
# But not right at the foot of the sticker: a chat draws its message timestamp over the
# bottom-right corner, and at BAND_MARGIN the words reached down into it and were hidden behind
# the time. Lifting the band this far clear of the bottom puts the words above the timestamp
# whatever the phone's font size, while the badge art needs nothing — its words are centred.
BAND_FOOT = 54


def _s(value: float) -> int:
    return round(value * SCALE)


def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if path.exists():
            return ImageFont.truetype(str(path), size * SCALE)
    raise RuntimeError(f"no Vietnamese-capable font found in {FONT_CANDIDATES}")


def _largest_fitting(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    width: int,
    height: int,
    max_size: int = MAX_FONT_SIZE,
) -> int | None:
    """The biggest font size at which every line fits the given box, or None."""
    limit_width, limit_height = _s(width), _s(height)
    for size in range(max_size, 23, -2):
        font = _font(size)
        widest = max(draw.textlength(line, font=font) for line in lines)
        if widest <= limit_width and _s(size * LINE_SPACING) * len(lines) <= limit_height:
            return size
    return None


def _balanced_two_lines(draw: ImageDraw.ImageDraw, words: list[str]) -> list[str]:
    """Split at the break whose longest line is shortest, so the two halves look even."""

    def widest(lines: list[str]) -> float:
        font = _font(64)
        return max(draw.textlength(line, font=font) for line in lines)

    return min(
        ([" ".join(words[:cut]), " ".join(words[cut:])] for cut in range(1, len(words))),
        key=widest,
    )


def _chosen_layout(draw: ImageDraw.ImageDraw, status: str) -> tuple[list[str], int]:
    """The lines and the font size the status is written at inside a badge."""
    words = texts.STICKER_STATUS_TEXT[status].upper().split()
    layouts: list[list[str]] = [[" ".join(words)]]
    if len(words) > 1:
        layouts.append(_balanced_two_lines(draw, words))
    sizes = [_largest_fitting(draw, lines, TEXT_WIDTH, TEXT_HEIGHT) for lines in layouts]
    if sizes[0] is not None and (len(layouts) == 1 or sizes[0] >= SINGLE_LINE_MIN_SIZE):
        return layouts[0], sizes[0]
    if sizes[-1] is not None:
        return layouts[-1], sizes[-1]
    raise RuntimeError(f"cannot fit {status!r} into the badge")


def _draw_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    size: int,
    centre_y: float,
    colour: tuple[int, int, int, int] = WHITE,
) -> None:
    """Write the lines centred on `centre_y`, in final 512 px coordinates."""
    font = _font(size)
    line_height = _s(size * LINE_SPACING)
    top = _s(centre_y) - line_height * len(lines) / 2
    for index, line in enumerate(lines):
        draw.text(
            (CANVAS / 2, top + line_height * (index + 0.5)),
            line,
            font=font,
            fill=colour,
            anchor="mm",
        )


def render_status(status: str) -> Image.Image:
    """The shipped sticker for a status: a coloured badge with the status written on it."""
    image = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        [_s(6), _s(6), _s(SIZE - 6), _s(SIZE - 6)],
        radius=_s(112),
        fill=(*COLOURS[status], 255),
    )
    lines, size = _chosen_layout(draw, status)
    _draw_lines(draw, lines, size, SIZE / 2)
    return image.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def _square(image_bytes: bytes) -> Image.Image:
    """A photo cropped to a square, keeping the middle of it, at drawing scale."""
    with Image.open(io.BytesIO(image_bytes)) as opened:
        source = opened.convert("RGBA")
    side = min(source.size)
    left = (source.width - side) // 2
    top = (source.height - side) // 2
    return source.crop((left, top, left + side, top + side)).resize(
        (CANVAS, CANVAS), Image.Resampling.LANCZOS
    )


def render_cover(image_bytes: bytes, status: str) -> Image.Image:
    """A square cover with the status written on a band along its foot.

    The band is opaque on purpose: the words have to stay readable over whatever the photo
    happens to be, and a translucent one would fail on a light or a busy picture.
    """
    image = _square(image_bytes)
    draw = ImageDraw.Draw(image)
    band_bottom = SIZE - BAND_FOOT
    band_top = band_bottom - BAND_HEIGHT
    draw.rounded_rectangle(
        [_s(BAND_MARGIN), _s(band_top), _s(SIZE - BAND_MARGIN), _s(band_bottom)],
        radius=_s(36),
        fill=(*COLOURS[status], 255),
    )
    words = texts.STICKER_STATUS_TEXT[status].upper().split()
    layouts: list[list[str]] = [[" ".join(words)]]
    if len(words) > 1:
        layouts.append(_balanced_two_lines(draw, words))
    box_width = SIZE - 2 * BAND_MARGIN - 24
    sizes = [_largest_fitting(draw, lines, box_width, BAND_HEIGHT, 72) for lines in layouts]
    if sizes[0] is not None:
        lines, size = layouts[0], sizes[0]
    elif sizes[-1] is not None:
        lines, size = layouts[-1], sizes[-1]
    else:
        raise RuntimeError(f"cannot fit {status!r} into the band")
    _draw_lines(draw, lines, size, band_top + BAND_HEIGHT / 2)
    return image.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def webp_bytes(image: Image.Image) -> bytes:
    """The bytes Telegram accepts: 512 px, transparent where it should be, well under 512 KB."""
    buffer = io.BytesIO()
    image.save(buffer, "WEBP", lossless=True, method=6)
    return buffer.getvalue()


def cover_bytes(image_bytes: bytes) -> bytes:
    """A photo, square and small enough to keep as a parcel's cover."""
    return webp_bytes(_square(image_bytes).resize((SIZE, SIZE), Image.Resampling.LANCZOS))


def sticker_bytes(image_bytes: bytes, status: str) -> bytes:
    """A photo with the status written on it, ready to upload as that parcel's sticker."""
    return webp_bytes(render_cover(image_bytes, status))


def status_bytes(status: str) -> bytes:
    """The shipped sticker for a status, ready to upload."""
    return webp_bytes(render_status(status))


def font_name() -> str:
    """Which font the art was drawn with — logged once, so a missing font is diagnosable."""
    for path in FONT_CANDIDATES:
        if path.exists():
            return path.name
    return "none"
