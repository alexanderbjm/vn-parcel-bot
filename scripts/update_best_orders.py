#!/usr/bin/env python3
"""Update BEST Express parcel and tracking events in vn-parcel-bot database

using the Playwright Bot Bypass stealth fetcher.

Usage:
    python scripts/update_best_orders.py <TRACKING_CODE> [--proxy <PROXY_URL>]
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

# Ensure vn_parcel_bot package is on sys.path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))

from vn_parcel_bot.carriers.models import TrackingEvent  # noqa: E402
from vn_parcel_bot.db.repo import Repository  # noqa: E402


def run_playwright_fetch(code: str, proxy: str | None = None) -> list[dict] | None:
    skill_node_modules = r"C:\Users\hozkg\.agents\skills\playwright-bot-bypass\node_modules"
    script_path = repo_root / "scripts" / "fetch_best_playwright.mjs"

    cmd = ["node", str(script_path), code]
    if proxy:
        cmd.extend(["--proxy", proxy])

    env = os.environ.copy()
    env["NODE_PATH"] = skill_node_modules

    print(f"[Bridge] Running Playwright stealth fetcher for: {code}...")
    result = subprocess.run(cmd, env=env, check=False)  # noqa: S603
    if result.returncode != 0:
        print(f"[Bridge] Playwright process exited with code {result.returncode}")

    json_file = repo_root / "data" / f"best_{code}.json"
    if not json_file.exists():
        print(f"[Bridge] Output file not found: {json_file}")
        return None

    try:
        data = json.loads(json_file.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else None
    except Exception as exc:
        print(f"[Bridge] Failed to parse JSON result: {exc}")
        return None


def parse_best_traces(traces: list[dict]) -> list[TrackingEvent]:
    events: list[TrackingEvent] = []
    for item in traces:
        time_str = item.get("actionTime") or item.get("time")
        if not time_str:
            continue
        try:
            # Format: "2026-09-14 15:30:00"
            parsed = datetime.strptime(time_str.strip(), "%Y-%m-%d %H:%M:%S")
            event_time = parsed.replace(tzinfo=UTC)
        except ValueError:
            try:
                event_time = datetime.fromisoformat(time_str).replace(tzinfo=UTC)
            except ValueError:
                event_time = datetime.now(UTC)

        desc = (item.get("description") or item.get("actionName") or "").strip()
        loc = (item.get("siteName") or item.get("city") or "").strip() or None
        raw = item.get("actionCode") or item.get("status") or None

        events.append(
            TrackingEvent(
                time=event_time,
                description=desc,
                location=loc,
                raw_status=str(raw) if raw else None,
            )
        )
    return events


async def update_database(code: str, express_list: list[dict]) -> None:
    load_dotenv()
    db_path = repo_root / os.environ.get("DB_PATH", "data/bot.sqlite3")
    if not db_path.exists():
        print(f"[DB] Database not found at: {db_path}")
        return

    repo = await Repository.open(db_path)
    now = datetime.now(UTC)
    try:
        for parcel_item in express_list:
            bill_no = parcel_item.get("expressId") or code
            traces = parcel_item.get("traces") or []
            events = parse_best_traces(traces)

            # Look up any parcels tracking this number
            rows = await repo._fetchall(
                "SELECT id, user_id, state FROM parcels WHERE tracking_number = ?",
                (bill_no,),
            )
            if not rows:
                print(f"[DB] No existing parcel in DB for tracking number: {bill_no}")
                continue

            for row in rows:
                parcel_id = row["id"]
                inserted = await repo.insert_events(parcel_id, events, now)
                print(f"[DB] Parcel #{parcel_id}: inserted {len(inserted)} new events")

                latest = events[0] if events else None
                if latest:
                    status_text = latest.description
                    is_delivered = any(
                        k in status_text.lower() for k in ("đã giao", "ký nhận", "thành công")
                    )
                    new_state = "delivered" if is_delivered else "in_transit"

                    await repo._write(
                        "UPDATE parcels SET carrier = 'best', state = ?, last_status_text = ?, "
                        "last_event_at = ?, updated_at = ? WHERE id = ?",
                        (
                            new_state,
                            status_text,
                            latest.time.isoformat(),
                            now.isoformat(),
                            parcel_id,
                        ),
                    )
                    print(f"[DB] Parcel #{parcel_id} state updated to '{new_state}'")

    finally:
        await repo.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Update BEST Express orders via Playwright")
    parser.add_argument("code", help="Tracking code (e.g. 841000072647)")
    parser.add_argument("--proxy", help="Optional proxy server URL (e.g. http://127.0.0.1:8080)")
    args = parser.parse_args()

    express_list = run_playwright_fetch(args.code, args.proxy)
    if not express_list:
        print("[Error] Could not retrieve tracking events.")
        sys.exit(1)

    asyncio.run(update_database(args.code, express_list))
    print("[Success] All matching orders updated in the database.")


if __name__ == "__main__":
    main()
