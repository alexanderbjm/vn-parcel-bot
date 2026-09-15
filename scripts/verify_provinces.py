"""Check PROVINCES against Nominatim: prints entries more than 25 km from OpenStreetMap's answer.

One-off maintenance script (about 70 requests, 1.1 s apart); not part of the test suite.
"""

import sys
import time

import httpx

from vn_parcel_bot.services.geo import haversine_km
from vn_parcel_bot.services.geo_provinces import PROVINCES

HEADERS = {"User-Agent": "vn-parcel-bot/0.1 (personal Telegram parcel tracker)"}
SEARCH_URL = "https://nominatim.openstreetmap.org/search"


def main() -> int:
    bad = 0
    with httpx.Client(headers=HEADERS, timeout=10) as client:
        for code, (name, lat, lon) in sorted(PROVINCES.items()):
            params = {"q": name, "countrycodes": "vn", "format": "jsonv2", "limit": 1}
            hits = client.get(SEARCH_URL, params=params).json()
            time.sleep(1.1)
            if not hits:
                print(f"{code} {name}: not found on OSM")
                bad += 1
                continue
            osm = (float(hits[0]["lat"]), float(hits[0]["lon"]))
            km = haversine_km((lat, lon), osm)
            if km > 25:
                print(f"{code} {name}: {km:.0f} km off; OSM {osm[0]:.4f}, {osm[1]:.4f}")
                bad += 1
    print("entries needing a fix:", bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
