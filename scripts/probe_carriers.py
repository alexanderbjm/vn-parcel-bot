"""Live probe of carrier tracking endpoints and Telegram (manual use; BUILD_PLAN.md Prompt 10A).

Never prints response bodies, full tracking codes, or the bot token.
"""

import argparse
import asyncio
import hashlib
import json
import os
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from vn_parcel_bot.carriers.http import make_http_client
from vn_parcel_bot.config import ConfigError, Settings

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "tests" / "fixtures" / "_raw"
PROBE_CARRIERS = ("spx", "jt", "cainiao", "fourpx", "ninjavan", "ghn", "best")
NOT_FOUND_MARKER = "Không tìm thấy dữ liệu"


def mask(code: str) -> str:
    return f"{code[:5]}…{code[-3:]}"


def load_settings(*, require_token: bool) -> Settings:
    load_dotenv(ROOT / ".env")
    try:
        return Settings.from_env(os.environ)
    except ConfigError:
        if require_token:
            raise
        return Settings(telegram_bot_token="", admin_telegram_id=0)


def parse_probe_file(path: Path) -> list[tuple[str, str, str | None]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split("#", 1)[0].split()
        if len(parts) < 2:
            continue
        carrier, code = parts[0].lower(), parts[1].upper()
        if carrier not in PROBE_CARRIERS:
            raise SystemExit(
                f"unknown carrier {carrier!r} (use one of {', '.join(PROBE_CARRIERS)})"
            )
        last4 = parts[2] if len(parts) > 2 and parts[2].isdigit() and len(parts[2]) == 4 else None
        rows.append((carrier, code, last4))
    return rows


def build_request(
    carrier: str, code: str, last4: str | None, spx_secret: str | None
) -> tuple[str, str, dict[str, Any], str]:
    if carrier == "spx":
        value = code
        if spx_secret:
            ts = int(time.time())
            value = f"{code}|{ts}{hashlib.sha256(f'{code}{ts}{spx_secret}'.encode()).hexdigest()}"
        return (
            "GET",
            "https://spx.vn/api/v2/fleet_order/tracking/search",
            {"params": {"sls_tracking_number": value}},
            "json",
        )
    if carrier == "jt":
        params = {"type": "track", "billcode": code, "cellphone": last4 or ""}
        return "GET", "https://jtexpress.vn/tracking", {"params": params}, "html"
    if carrier == "cainiao":
        params = {"mailNos": code, "lang": "en-US", "language": "en-US"}
        return "GET", "https://global.cainiao.com/global/detail.json", {"params": params}, "json"
    if carrier == "fourpx":
        body = {"queryCodes": [code], "language": "en-us", "translateLanguage": "en-us"}
        return "POST", "https://track.4px.com/track/v2/front/listTrackV3", {"json": body}, "json"
    if carrier == "ninjavan":
        return (
            "GET",
            "https://api.ninjavan.co/vn/dash/1.2/public/orders",
            {"params": {"tracking_id": code}},
            "json",
        )
    if carrier == "ghn":
        body: dict[str, str] = {"order_code": code}
        if last4:
            body["phone_verify"] = hashlib.sha256(f"{code}|{last4}".encode()).hexdigest()
        return (
            "POST",
            "https://fe-online-gateway.ghn.vn/order-tracking/public-api/client/tracking-logs",
            {"json": body},
            "json",
        )
    return "GET", "https://www.best-inc.vn/track", {"params": {"bills": code}}, "html"


def _dig(payload: Any, *path: str | int) -> Any:
    for step in path:
        if isinstance(step, int):
            if not isinstance(payload, list) or len(payload) <= step:
                return None
        elif not isinstance(payload, dict):
            return None
        payload = payload[step] if isinstance(step, int) else payload.get(step)
    return payload


def event_count(carrier: str, payload: Any) -> int | None:
    paths: dict[str, tuple[str | int, ...]] = {
        "spx": ("data", "tracking_list"),
        "cainiao": ("module", 0, "detailList"),
        "fourpx": ("data", 0, "tracks"),
        "ninjavan": ("events",),
        "ghn": ("data", "tracking_logs"),
    }
    if carrier not in paths:
        return None
    events = _dig(payload, *paths[carrier])
    if events is None and carrier == "ninjavan":
        events = _dig(payload, "data", "events")
    return len(events) if isinstance(events, list) else None


def structural_hint(carrier: str, text: str, kind: str) -> str:
    if kind == "html":
        return (
            f"not_found_marker={NOT_FOUND_MARKER in text} "
            f"result_tracking={'result-tracking' in text}"
        )
    try:
        payload = json.loads(text)
    except ValueError:
        return f"invalid json (starts with {text.lstrip()[:1]!r})"
    keys = sorted(payload) if isinstance(payload, dict) else type(payload).__name__
    return f"keys={keys} events={event_count(carrier, payload)}"


async def probe_carriers(args: argparse.Namespace) -> None:
    settings = load_settings(require_token=False)
    rows = parse_probe_file(Path(args.file))
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    last_carrier: str | None = None
    async with make_http_client(settings) as http:
        for carrier, code, last4 in rows:
            if carrier == last_carrier:
                await asyncio.sleep(3 + random.random() * 2)
            last_carrier = carrier
            method, url, kwargs, kind = build_request(carrier, code, last4, args.spx_secret)
            try:
                response = await http.request(method, url, **kwargs)
            except httpx.HTTPError as exc:
                print(f"{carrier:9} {mask(code)} ERROR {type(exc).__name__}")
                continue
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            raw = RAW_DIR / f"{carrier}_{code[:5]}x{code[-3:]}_{stamp}.{kind}"
            raw.write_bytes(response.content)
            hint = structural_hint(carrier, response.text, kind)
            print(
                f"{carrier:9} {mask(code)} HTTP {response.status_code} "
                f"{len(response.content)} bytes {hint}"
            )


async def probe_telegram() -> None:
    settings = load_settings(require_token=True)
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/getMe"
    try:
        async with httpx.AsyncClient(
            timeout=settings.http_timeout_seconds, proxy=settings.telegram_proxy_url
        ) as client:
            data = (await client.get(url)).json()
    except Exception as exc:
        print(type(exc).__name__)
        return
    if data.get("ok"):
        print(f"OK @{data['result']['username']}")
    else:
        print(f"FAILED error_code={data.get('error_code')}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    carriers = sub.add_parser("carriers", help="probe carrier endpoints with real codes")
    carriers.add_argument("--file", default=str(ROOT / "probe_codes.local.txt"))
    carriers.add_argument("--parse", action="store_true", help="also run the carrier parsers")
    carriers.add_argument("--spx-secret", default=None, help="sign SPX requests with this secret")
    sub.add_parser("telegram", help="check that the bot token works (getMe)")
    args = parser.parse_args()
    if args.command == "carriers":
        asyncio.run(probe_carriers(args))
    else:
        asyncio.run(probe_telegram())


if __name__ == "__main__":
    main()
