#!/usr/bin/env python3
"""Draw the delivery-status stickers that ship with the bot.

    python scripts/make_status_stickers.py [--out src/vn_parcel_bot/assets/status]

One 512x512 transparent WEBP per status in ``STICKER_STATUSES``. Drawn rather than sourced:
these are flat shapes, and drawing them keeps the art licence-free, reproducible and easy to
recolour. Telegram shows a sticker at 512 px on its longest side and refuses one over 512 KB
(§9.13), so every file is 512x512 RGBA.

Everything is drawn at ``SCALE`` times the final size and shrunk with LANCZOS: PIL has no
antialiasing, and a circle drawn at 512 px alone shows a stepped edge.
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 512
SCALE = 4
WHITE = (255, 255, 255, 255)

# One colour per status: blue on the way, orange nearly there, green delivered, red back.
COLOURS = {
    "moving": (47, 107, 255),
    "near": (255, 138, 0),
    "delivered": (34, 180, 90),
    "returned": (229, 72, 77),
}
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "src" / "vn_parcel_bot" / "assets" / "status"


def _s(value: float) -> int:
    return round(value * SCALE)


def _badge(colour: tuple[int, int, int]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGBA", (SIZE * SCALE, SIZE * SCALE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        [_s(6), _s(6), _s(SIZE - 6), _s(SIZE - 6)], radius=_s(112), fill=(*colour, 255)
    )
    return image, draw


def _moving(draw: ImageDraw.ImageDraw, colour: tuple[int, int, int]) -> None:
    """A box van, moving right."""
    draw.rounded_rectangle([_s(146), _s(186), _s(318), _s(296)], radius=_s(16), fill=WHITE)
    draw.rounded_rectangle([_s(318), _s(224), _s(382), _s(296)], radius=_s(14), fill=WHITE)
    draw.rectangle([_s(330), _s(240), _s(368), _s(268)], fill=(*colour, 255))
    for centre in (196, 328):
        draw.ellipse([_s(centre - 27), _s(289), _s(centre + 27), _s(343)], fill=WHITE)
        draw.ellipse([_s(centre - 9), _s(307), _s(centre + 9), _s(325)], fill=(*colour, 255))


def _near(draw: ImageDraw.ImageDraw, colour: tuple[int, int, int]) -> None:
    """A map pin, with the badge showing through its middle."""
    draw.ellipse([_s(164), _s(118), _s(348), _s(302)], fill=WHITE)
    draw.polygon([(_s(256), _s(398)), (_s(196), _s(252)), (_s(316), _s(252))], fill=WHITE)
    draw.ellipse([_s(216), _s(170), _s(296), _s(250)], fill=(*colour, 255))


def _p(point: tuple[float, float]) -> tuple[int, int]:
    return _s(point[0]), _s(point[1])


def _delivered(draw: ImageDraw.ImageDraw) -> None:
    """A tick."""
    start, corner, end = (158, 262), (226, 334), (358, 176)
    draw.line([_p(start), _p(corner), _p(end)], fill=WHITE, width=_s(48), joint="curve")
    # PIL draws square ends; a disc on each end rounds the tick off.
    for x, y in (start, end):
        draw.ellipse([_s(x - 24), _s(y - 24), _s(x + 24), _s(y + 24)], fill=WHITE)


def _returned(draw: ImageDraw.ImageDraw) -> None:
    """A U-turn: up one side, over the top and back down, with the arrow at the end.

    Both legs are the same length and the arrowhead is about one and a half stroke widths
    wide, so the turn reads as one shape rather than an arc with a wedge stuck on it.
    """
    draw.arc([_s(184), _s(148), _s(328), _s(292)], start=180, end=360, fill=WHITE, width=_s(44))
    draw.line([_p((184, 220)), _p((184, 332))], fill=WHITE, width=_s(44))
    draw.line([_p((328, 220)), _p((328, 332))], fill=WHITE, width=_s(44))
    draw.polygon([_p((150, 330)), _p((218, 330)), _p((184, 388))], fill=WHITE)


def draw_status(status: str) -> Image.Image:
    colour = COLOURS[status]
    image, draw = _badge(colour)
    if status == "moving":
        _moving(draw, colour)
    elif status == "near":
        _near(draw, colour)
    elif status == "delivered":
        _delivered(draw)
    else:
        _returned(draw)
    return image.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"default: {DEFAULT_OUT}")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for status in COLOURS:
        path = args.out / f"{status}.webp"
        draw_status(status).save(path, "WEBP", lossless=True, method=6)
        print(f"{path}  {path.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
