# Command Code Project Guidelines - VN Parcel Bot

## Core Directive: Parcel Tracking & Order Updates

When asked to check, track, look up, or update an order or parcel tracking code (e.g. `SPXVN...`, `JNTX...`, `BEST...`, `LP...`, `84...`):

**DO NOT ATTEMPT TO SCRAPE CARRIER WEBSITES DIRECTLY.**
Carriers like BEST Express (`best-inc.vn`) and affiliate mirrors like `vntracuu.com` deploy strict anti-bot security (Alibaba/BEST rotate & slide CAPTCHAs, `risk_001`, or missing assets). Headless scrapers will fail or get blocked.

**ALWAYS DELEGATE TRACKING QUERIES TO THE LOCAL VN PARCEL BRIDGE:**

### Method 1: Local CLI Bridge (Recommended)
Run the bridge script directly in bash/cmd:
```bash
.\.venv\Scripts\python scripts/query_order.py <TRACKING_CODE>
```
- For carriers requiring phone digits (e.g., J&T domestic, GHN):
  ```bash
  .\.venv\Scripts\python scripts/query_order.py <TRACKING_CODE> --phone <LAST4>
  ```
- For captcha-protected carriers like BEST Express:
  ```bash
  .\.venv\Scripts\python scripts/query_order.py <TRACKING_CODE> --stealth
  ```

### Method 2: Local Proxy Endpoint (HTTP)
If the background proxy service is running on port 8766:
```bash
curl -s "http://127.0.0.1:8766/track?code=<TRACKING_CODE>"
```
Query parameters:
- `code`: Tracking number (required)
- `phone`: Last 4 digits of phone number (optional)
- `stealth`: `1` or `true` to invoke Playwright stealth bypass

### Method 3: MCP Tool (If registered)
Call the `track_parcel` tool:
```json
{
  "code": "<TRACKING_CODE>",
  "phone": "<LAST4>",
  "stealth": false
}
```

---

## Output Format
Always present tracking updates cleanly to the user:
- **Carrier**: Detected carrier name (e.g. SPX Express, BEST Express, J&T)
- **Status**: Latest milestone (e.g. "Giao hàng thành công", "Đang giao hàng")
- **Delivered**: Yes / No
- **Timeline**: Chronological list of the most recent transit checkpoints with timestamps.

---

## Project Structure & Conventions
- **Virtualenv**: `.\.venv\Scripts\python.exe`
- **Database**: SQLite database at `data/bot.sqlite3`
- **Testing**: `pytest`
- **Linting & Formatting**: `ruff check .` and `ruff format .`
