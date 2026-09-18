#!/usr/bin/env python3
"""Draw the delivery-status stickers that ship with the bot.

    python scripts/make_status_stickers.py [--out src/vn_parcel_bot/assets/status]

One 512x512 transparent WEBP per status in ``services.stickers.STICKER_STATUSES``, carrying the
status in Vietnamese — the sticker lands next to a message read in Vietnamese, and the four
words say what happened faster than any pictogram did. The wording comes from
``texts.STICKER_STATUS_TEXT``, so the image and the `/sticker` list can never drift apart.

Drawn rather than sourced: these are flat shapes and text, and drawing them keeps the art
licence-free (only a system font is used, and only its rendered output ships), reproducible, and
easy to recolour. Telegram shows a sticker at 512 px on its longest side and refuses one over
512 KB (§9.13), so every file is 512x512 RGBA.

Everything is drawn at ``SCALE`` times the final size and shrunk with LANCZOS: PIL has no
antialiasing, and a circle drawn at 512 px alone shows a stepped edge.
"""

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from vn_parcel_bot.services.stickers import STICKER_STATUSES  # noqa: E402
from vn_parcel_bot.texts import STICKER_STATUS_TEXT  # noqa: E402

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
# Room for the text inside the badge, in final 512 px coordinates.
MAX_FONT_SIZE = 120
TEXT_WIDTH = 372
TEXT_HEIGHT = 300
LINE_SPACING = 1.14
# One line reads better than two, but only while it stays big: "SẮP GIAO" fits on one line at
# ~75 px, while "ĐANG TRÊN ĐƯỜNG" would drop to ~48 px to do so, and two lines give it ~90.
SINGLE_LINE_MIN_SIZE = 64
DEFAULT_OUT = REPO_ROOT / "src" / "vn_parcel_bot" / "assets" / "status"


def _s(value: float) -> int:
    return round(value * SCALE)


def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if path.exists():
            return ImageFont.truetype(str(path), size * SCALE)
    raise SystemExit(f"no Vietnamese-capable font found in {FONT_CANDIDATES}")


def _badge(colour: tuple[int, int, int]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        [_s(6), _s(6), _s(SIZE - 6), _s(SIZE - 6)], radius=_s(112), fill=(*colour, 255)
    )
    return image, draw


def _largest_fitting(draw: ImageDraw.ImageDraw, lines: list[str]) -> int | None:
    """The biggest font size at which every line fits the badge, or None."""
    limit_width, limit_height = _s(TEXT_WIDTH), _s(TEXT_HEIGHT)
    for size in range(MAX_FONT_SIZE, 23, -2):
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


def draw_status(status: str) -> Image.Image:
    """The badge with the status written on it, as large as the badge allows."""
    image, draw = _badge(COLOURS[status])
    words = STICKER_STATUS_TEXT[status].upper().split()
    layouts: list[list[str]] = [[" ".join(words)]]
    if len(words) > 1:
        layouts.append(_balanced_two_lines(draw, words))
    sizes = [_largest_fitting(draw, lines) for lines in layouts]
    if sizes[0] is not None and (len(layouts) == 1 or sizes[0] >= SINGLE_LINE_MIN_SIZE):
        lines, size = layouts[0], sizes[0]
    elif sizes[-1] is not None:
        lines, size = layouts[-1], sizes[-1]
    else:
        raise SystemExit(f"cannot fit {status!r} into the badge")

    font = _font(size)
    line_height = _s(size * LINE_SPACING)
    top = (CANVAS - line_height * len(lines)) / 2
    for index, line in enumerate(lines):
        draw.text(
            (CANVAS / 2, top + line_height * (index + 0.5)),
            line,
            font=font,
            fill=WHITE,
            anchor="mm",
        )
    return image.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"default: {DEFAULT_OUT}")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for status in STICKER_STATUSES:
        path = args.out / f"{status}.webp"
        draw_status(status).save(path, "WEBP", lossless=True, method=6)
        print(f"{path}  {path.stat().st_size} bytes  {STICKER_STATUS_TEXT[status]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
