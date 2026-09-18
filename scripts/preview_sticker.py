#!/usr/bin/env python3
"""Show the sticker the bot would send for a parcel, without going through Telegram.

    python scripts/preview_sticker.py <ref> [<ref> ...] [--out data/preview] [--send]

A ref is a parcel id, a label ("Aula F75") or a tracking code. One PNG per matching parcel is
written to `--out` (`data/preview` by default, which is gitignored with `data/`), showing the
picture the bot would upload for it: the parcel's own cover with the status written on it when it
has one, else the shipped sticker.

`--send` also posts each one to the admin's own chat, as the sticker Telegram will actually show
rather than as a file to open — that is what makes it a preview of the real thing.

A sticker the admin mapped with `/sticker` is a Telegram `file_id` — nothing to draw — so the
script says so instead of silently showing something else. The status and the source of the
picture are printed either way.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telegram import Bot

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from vn_parcel_bot.db.repo import Repository  # noqa: E402
from vn_parcel_bot.services.sticker_art import (  # noqa: E402
    render_cover,
    render_status,
    webp_bytes,
)
from vn_parcel_bot.services.stickers import (  # noqa: E402
    MANUAL_KEY,
    cover_path,
    covers_dir,
    icon_statuses,
    sticker_status,
)
from vn_parcel_bot.texts import STICKER_STATUS_TEXT  # noqa: E402

DEFAULT_OUT = Path("data/preview")
# A sticker only ever goes out with an update, and an update only comes from one of these states:
# a pending parcel has nothing new to say, and an expired or stale one is announced by its own
# message, without a sticker (§6.3).
ANNOUNCED_STATES = ("in_transit", "delivered", "returned")


def matching(rows: list, ref: str) -> list:
    """Every parcel a ref names: its id, its label (whole, ignoring case) or its code."""
    wanted = ref.strip()
    lowered = wanted.casefold()
    numeric = int(wanted) if wanted.isdigit() else None
    found = []
    for row in rows:
        if (
            (numeric is not None and int(row["id"]) == numeric)
            or (row["label"] or "").casefold() == lowered
            or row["tracking_number"].casefold() == lowered
        ):
            found.append(row)
    return found


async def preview(repo: Repository, row: object, out: Path, directory: Path, send: bool) -> None:
    parcel_id = int(row["id"])  # type: ignore[index]
    label = row["label"] or row["tracking_number"]  # type: ignore[index]
    status = sticker_status(row["state"], row["progress"])  # type: ignore[index]
    where = f"#{parcel_id} {label} · state={row['state']} progress={row['progress']}"  # type: ignore[index]

    cover = cover_path(directory, parcel_id)
    manual = await repo.get_meta(f"{MANUAL_KEY}{status}")
    if cover.exists():
        image, source = render_cover(cover.read_bytes(), status), "its own cover"
    elif manual:
        print(f"{where} -> {status}: /sticker has a file_id for it ({manual[:14]}…)")
        print("   nothing to draw — the admin's own sticker is a Telegram file_id")
        return
    elif status in icon_statuses():
        image, source = render_status(status), "the shipped sticker"
    else:
        print(f"{where} -> {status}: no sticker would be sent")
        return

    path = out / f"parcel-{parcel_id}.png"
    image.save(path, "PNG")
    print(f"{where} -> {status} ({STICKER_STATUS_TEXT[status]}) from {source}")
    never_announced = row["state"] not in ANNOUNCED_STATES  # type: ignore[index]
    if never_announced:
        print(f"   state={row['state']} is never announced, so nothing is sent for it now")  # type: ignore[index]
    print(f"   {path}  {path.stat().st_size} bytes  {image.width}x{image.height}")
    if send:
        caption = f"{where} → {status} ({STICKER_STATUS_TEXT[status]}) · {source}"
        if never_announced:
            caption += "\n(nothing is sent while it is pending — this is what it would send)"
        await send_to_admin(webp_bytes(image), caption)


async def send_to_admin(image_bytes: bytes, caption: str) -> None:
    """Post one sticker to the admin's chat, as Telegram will show it rather than as a file."""
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    admin = (os.environ.get("ADMIN_TELEGRAM_ID") or "").strip()
    if not token or not admin:
        raise SystemExit("TELEGRAM_BOT_TOKEN and ADMIN_TELEGRAM_ID must be set to use --send")
    async with Bot(token) as bot:
        said = await bot.send_message(int(admin), caption)
        await bot.send_sticker(int(admin), sticker=image_bytes, reply_to_message_id=said.message_id)
    print(f"   sent to admin ({admin})")


async def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("refs", nargs="+", help="parcel id, label or tracking code")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"default: {DEFAULT_OUT}")
    parser.add_argument(
        "--send", action="store_true", help="also post each sticker to the admin's own chat"
    )
    args = parser.parse_args()

    db_path = Path(os.environ.get("DB_PATH", "data/bot.sqlite3"))
    repo = await Repository.open(db_path)
    try:
        rows = await repo._fetchall(
            "SELECT id, label, tracking_number, state, progress FROM parcels ORDER BY id"
        )
        args.out.mkdir(parents=True, exist_ok=True)
        for ref in args.refs:
            found = matching(rows, ref)
            if not found:
                print(f"{ref}: no parcel matches")
                continue
            for row in found:
                await preview(repo, row, args.out, covers_dir(db_path), args.send)
    finally:
        await repo.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
