#!/usr/bin/env python3
"""Draw the delivery-status stickers that ship with the bot.

    python scripts/make_status_stickers.py [--out src/vn_parcel_bot/assets/status]

One 512x512 transparent WEBP per status in ``services.stickers.STICKER_STATUSES``, carrying the
status in Vietnamese — the sticker lands next to a message read in Vietnamese, and the words say
what happened faster than a pictogram did. The wording comes from ``texts.STICKER_STATUS_TEXT``,
so the drawing and the `/sticker` list cannot drift apart.

The drawing itself lives in ``services/sticker_art.py``: the bot needs the same words at runtime,
both to stamp a status onto a cover the admin sends to `/sticker` and onto a parcel's own
screenshot. One renderer, so the shipped art and a custom cover cannot disagree.
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from vn_parcel_bot.services.sticker_art import status_bytes  # noqa: E402
from vn_parcel_bot.services.stickers import STICKER_STATUSES  # noqa: E402
from vn_parcel_bot.texts import STICKER_STATUS_TEXT  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "src" / "vn_parcel_bot" / "assets" / "status"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"default: {DEFAULT_OUT}")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for status in STICKER_STATUSES:
        path = args.out / f"{status}.webp"
        path.write_bytes(status_bytes(status))
        print(f"{path}  {path.stat().st_size} bytes  {STICKER_STATUS_TEXT[status]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
