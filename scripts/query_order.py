#!/usr/bin/env python3
"""Query parcel tracking information and serve as an agent/proxy bridge.

Usage:
    # CLI Query:
    python scripts/query_order.py <TRACKING_CODE> [--phone <LAST4>]

    # Local Proxy Server (for Claude / Agents):
    python scripts/query_order.py --serve [--port 8766]
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from dotenv import load_dotenv

# Ensure vn_parcel_bot is importable
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))

from vn_parcel_bot.carriers.models import TrackingResult  # noqa: E402
from vn_parcel_bot.carriers.registry import CarrierRegistry  # noqa: E402
from vn_parcel_bot.db.repo import Repository  # noqa: E402
from vn_parcel_bot.tracking_codes import detect_carriers, normalize_code  # noqa: E402

log = logging.getLogger("parcel_bridge")


async def query_tracking(
    code: str,
    phone_last4: str | None = None,
    stealth: bool = False,
    proxy: str | None = None,
) -> dict:
    load_dotenv()
    normalized = normalize_code(code)
    registry = CarrierRegistry.load()
    snapshot = registry.current

    detection = snapshot.detect(normalized)
    candidates = detection.candidates if detection else detect_carriers(normalized)

    # 1. Check local database first
    db_path = repo_root / os.environ.get("DB_PATH", "data/bot.sqlite3")
    if db_path.exists():
        try:
            repo = await Repository.open(db_path)
            row = await repo._fetchone(
                "SELECT id, carrier, state, last_status_text, last_event_at FROM parcels "
                "WHERE tracking_number = ?",
                (normalized,),
            )
            if row:
                events = await repo.list_events(row["id"], limit=20)
                await repo.close()
                return {
                    "tracking_number": normalized,
                    "carrier": row["carrier"],
                    "found": True,
                    "state": row["state"],
                    "status": row["last_status_text"],
                    "source": "local_db",
                    "events": [
                        {
                            "time": e.time.isoformat() if e.time else None,
                            "description": e.description,
                            "location": e.location,
                            "raw_status": e.raw_status,
                        }
                        for e in events
                    ],
                }
            await repo.close()
        except Exception as exc:
            log.debug("Local db lookup error: %s", exc)

    # 2. Query live via registered carrier clients
    async with httpx.AsyncClient(timeout=15.0) as http:
        for carrier_code in candidates:
            client = snapshot.client(carrier_code)
            if not client:
                continue

            try:
                result: TrackingResult = await client.fetch(
                    http, normalized, phone_last4=phone_last4
                )
                if result.found:
                    return {
                        "tracking_number": normalized,
                        "carrier": carrier_code,
                        "found": True,
                        "delivered": result.delivered,
                        "returned": result.returned,
                        "status": result.latest.description if result.latest else None,
                        "source": "live_carrier",
                        "events": [
                            {
                                "time": e.time.isoformat() if e.time else None,
                                "description": e.description,
                                "location": e.location,
                                "raw_status": e.raw_status,
                            }
                            for e in result.events
                        ],
                    }
            except Exception as exc:
                log.debug("Carrier fetch error %s: %s", carrier_code, exc)
                continue

    # 3. Check for locally cached Playwright output (e.g. data/best_<code>.json)
    cached_file = repo_root / "data" / f"best_{normalized}.json"
    if cached_file.exists():
        try:
            items = json.loads(cached_file.read_text(encoding="utf-8"))
            if items and isinstance(items, list):
                item = items[0]
                traces = item.get("traces") or []
                return {
                    "tracking_number": normalized,
                    "carrier": "best",
                    "found": True,
                    "status": item.get("statusName"),
                    "source": "playwright_cache",
                    "events": traces,
                }
        except Exception as exc:
            log.debug("Cache read error: %s", exc)

    # 4. If stealth requested (e.g. for BEST Express bot bypass)
    if stealth:
        try:
            from scripts.update_best_orders import run_playwright_fetch, update_database

            items = run_playwright_fetch(normalized, proxy=proxy)
            if items and isinstance(items, list):
                await update_database(normalized, items)
                item = items[0]
                traces = item.get("traces") or []
                return {
                    "tracking_number": normalized,
                    "carrier": "best",
                    "found": True,
                    "status": item.get("statusName"),
                    "source": "playwright_stealth",
                    "events": traces,
                }
        except Exception as exc:
            log.warning("Stealth runner error: %s", exc)

    return {
        "tracking_number": normalized,
        "candidates": list(candidates),
        "found": False,
        "message": "Parcel tracking data not found or requires human verification.",
    }


class ProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/track", "/tracking", "/order"):
            qs = parse_qs(parsed.query)
            code = qs.get("code", [""])[0] or qs.get("num", [""])[0]
            phone = qs.get("phone", [None])[0]
            stealth = qs.get("stealth", ["0"])[0].lower() in ("1", "true", "yes")
            proxy = qs.get("proxy", [None])[0]

            if not code:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "Missing code query parameter"}')
                return

            result = asyncio.run(query_tracking(code, phone, stealth=stealth, proxy=proxy))
            body = json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok", "service": "vn-parcel-bridge"}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/track", "/order"):
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length)) if length else {}
            code = payload.get("code") or payload.get("tracking_number") or ""
            phone = payload.get("phone") or payload.get("phone_last4")
            stealth = bool(payload.get("stealth", False))
            proxy = payload.get("proxy")

            if not code:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "Missing code field in JSON body"}')
                return

            result = asyncio.run(query_tracking(code, phone, stealth=stealth, proxy=proxy))
            body = json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write(f"[Proxy] {self.address_string()} - {format % args}\n")


def run_server(port: int = 8766) -> None:
    server = HTTPServer(("127.0.0.1", port), ProxyHandler)
    print(f"[Parcel Bridge] Listening on http://127.0.0.1:{port}/track?code=<CODE>")
    print(f"[Parcel Bridge] Health check: http://127.0.0.1:{port}/health")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Parcel Bridge] Stopped.")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Query parcel tracking bridge")
    parser.add_argument("code", nargs="?", help="Tracking code to check")
    parser.add_argument("--phone", help="Phone last 4 digits (for carriers needing phone)")
    parser.add_argument(
        "--stealth",
        action="store_true",
        help="Use Playwright stealth bypass for captcha-protected carriers (e.g. BEST)",
    )
    parser.add_argument(
        "--proxy", help="Proxy URL for stealth fetcher (e.g. http://127.0.0.1:8080)"
    )
    parser.add_argument("--serve", action="store_true", help="Start local HTTP proxy server")
    parser.add_argument(
        "--port", type=int, default=8766, help="Port for proxy server (default: 8766)"
    )
    args = parser.parse_args()

    if args.serve:
        run_server(args.port)
        return

    if not args.code:
        parser.print_help()
        sys.exit(1)

    result = asyncio.run(
        query_tracking(args.code, args.phone, stealth=args.stealth, proxy=args.proxy)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
