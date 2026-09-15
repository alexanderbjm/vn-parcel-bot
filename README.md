# vn-parcel-bot

A personal Telegram bot that watches parcels bought online in Vietnam and messages you (and a few allowlisted family members) every time a new tracking event appears. It runs on a Windows PC, polls the carriers' public tracking endpoints, and uses Telegram long polling, so no server, domain or port forwarding is needed.

| Carrier | What the bot does |
|---|---|
| SPX Express, J&T Express, Cainiao, 4PX, Ninja Van, GHN | Tracks automatically and notifies on every new event |
| BEST Express, YunExpress, GHTK, Viettel Post, VNPost/EMS, LEX VN, SF Express | Recognises the code and replies with tracking links (their sites block automated lookups) |

Paste a tracking code and the bot works out the carrier. When a code could belong to several carriers (for example GHN and Ninja Van), it tries each one and keeps the carrier that returns data.

The full specification and build steps are in [`BUILD_PLAN.md`](BUILD_PLAN.md) (`SPEC.md` is a generated copy of its Part 2).

## Requirements

- Windows 10 or 11, Python 3.13, git
- A Telegram account, and Telegram reachable from this PC. Some Vietnamese ISPs block Telegram; if so, run a VPN client that offers a local HTTP or SOCKS5 proxy and set `TELEGRAM_PROXY_URL` (carrier lookups never use the proxy).

## Setup

1. **Create the bot.** In Telegram open **@BotFather** → `/newbot` → pick a name and a username ending in `bot` → copy the token. Then `/setjoingroups` → your bot → **Disable**.
2. **Get your Telegram ID.** Message **@userinfobot** and copy the `Id` number.
3. **Install.**
   ```powershell
   Set-Location $HOME\projects\vn-parcel-bot
   py -3.13 -m venv .venv
   .\.venv\Scripts\python -m pip install -e .
   Copy-Item .env.example .env
   notepad .env
   ```
4. **Fill `.env`.** Never share this file or paste the token anywhere.

   | Variable | Required | Default | Meaning |
   |---|---|---|---|
   | `TELEGRAM_BOT_TOKEN` | yes | – | Token from @BotFather |
   | `ADMIN_TELEGRAM_ID` | yes | – | Your numeric Telegram ID |
   | `POLL_INTERVAL_MINUTES` | no | `20` | Minutes between checks for parcels with no tracking data yet (5–240). Parcels in transit are checked every 10 minutes, and at the delivery hub or out for delivery every 3 minutes (never less often than this value) |
   | `REQUEST_DELAY_SECONDS` | no | `3` | Pause between requests to the same carrier |
   | `HTTP_TIMEOUT_SECONDS` | no | `15` | Carrier request timeout |
   | `DB_PATH` | no | `data/bot.sqlite3` | Database file |
   | `LOG_DIR` | no | `logs` | Log folder |
   | `LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR` |
   | `TIMEZONE` | no | `Asia/Ho_Chi_Minh` | Time zone for messages and quiet hours |
   | `QUIET_HOURS` | no | `22-7` | Local hours when messages arrive silently; empty disables |
   | `MAX_PARCELS_PER_USER` | no | `30` | Active parcels per person |
   | `TELEGRAM_PROXY_URL` | no | – | e.g. `socks5h://127.0.0.1:1080` if Telegram is blocked |
   | `DIGEST_TIMES` | no | `07:00,12:00,19:00,22:00` | Local times for the daily digest; empty disables it |
   | `VISION_ENGINE` | no | `claude_code` | `claude_code` reads screenshots with Claude Code on this PC (your Claude plan); `api` uses Anthropic API credit; `agy` uses Gemini through agy and the local OCR proxy (see *Screenshots*) |
   | `CLAUDE_CODE_PATH` | no | found automatically | Path to `claude.exe` if it is not on `PATH` or in `%USERPROFILE%\.local\bin` |
   | `VISION_MODEL` | no | `sonnet` | Claude Code model for screenshots (Haiku misread long codes) |
   | `VISION_TIMEOUT_SECONDS` | no | `90` | Seconds to wait for one screenshot (10..300); use `150` with `agy` |
   | `AGY_PROXY_URL` | no | `http://127.0.0.1:8765` | `agy` engine: address of the OCR proxy on this PC |
   | `AGY_PATH` | no | found automatically | OCR proxy: path to `agy.exe` if it is not on `PATH` or in `%LOCALAPPDATA%\agy\bin` |
   | `AGY_MODEL` | no | `gemini-3.8-flash-low` | OCR proxy: Gemini model for screenshots |
   | `AGY_FALLBACK_MODEL` | no | `gemini-3.7-flash-low` | OCR proxy: model tried once when the first one fails or times out; empty disables |
   | `ANTHROPIC_API_KEY` | no | – | `api` engine only |
   | `ANTHROPIC_MODEL` | no | `claude-haiku-4-5-20251001` | `api` engine only |
   | `ANTHROPIC_WORKSPACE_ID` | no | – | `api` engine only, for keys not scoped to a workspace |
   | `SEVENTEEN_TRACK_KEY` | no | – | 17TRACK API key: tracks BEST, SF and cross-border J&T (`JNTX…`, after the phone digits). Each newly registered parcel uses one 17TRACK quota |
   | `MAPS_ENABLED` | no | `true` | Hub lines, distances and map pictures (see *Maps and distance*); `false` turns them off |

5. **Check Telegram and carriers** (optional but recommended before the first run):
   ```powershell
   .\.venv\Scripts\python scripts\probe_carriers.py telegram
   ```
   For a live carrier check, put real codes in `probe_codes.local.txt` (one per line: `carrier code [last4]`) and run `.\.venv\Scripts\python scripts\probe_carriers.py carriers --parse`.
6. **First run in the foreground.**
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\run-bot.ps1
   ```
   Send `/start` to your bot. Stop with Ctrl+C.

## Start automatically at logon

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-task.ps1     # install and start
powershell -ExecutionPolicy Bypass -File scripts\status-bot.ps1       # task state, process, last log lines
powershell -ExecutionPolicy Bypass -File scripts\uninstall-task.ps1   # remove
powershell -ExecutionPolicy Bypass -File scripts\install-proxy-task.ps1                            # OCR proxy for VISION_ENGINE=agy
powershell -ExecutionPolicy Bypass -File scripts\uninstall-task.ps1 -TaskName "VN Parcel OCR Proxy"  # remove the OCR proxy
```

The task starts `pythonw.exe -m vn_parcel_bot` at logon, restarts it every minute if it crashes, and never starts a second copy. Keep the PC awake while plugged in (*Settings → System → Power & sleep → Sleep: Never*); after sleep or shutdown the bot catches up on its first check.

## Using the bot

| Command / Action | What it does |
|---|---|
| paste a code | Start tracking; the bot detects the carrier |
| send a photo/screenshot | Claude Vision extracts tracking code, carrier & phone digits and tracks it |
| `/track <mã> [4 số] [hãng]` | Track with phone digits and/or a forced carrier (`spx`, `jt`, `cainiao`, `4px`, `ninjavan`, `ghn`) |
| `/list` | Your parcels |
| `/status <mã hoặc số>` | Full history, newest first |
| `/label <mã hoặc số> [tên]` · reply `/label [tên]` | Name a parcel. Reply to a bot message to name the parcel in it; with no name the bot asks for one, with buttons to clear the name or cancel. If the replied message holds several parcels, buttons let you pick one. The label is shown with the tracking code blurred next to it, and your `/label` message is deleted |
| `/remove <số> [số…]` | Stop tracking one or more parcels (e.g. `/remove 1 2 3`, numbers from `/list`, or codes). The bot lists them and asks with ✅ Xóa / ↩ Hủy buttons. On `/list`, **🗑 Xóa nhiều** lets you tick parcels and remove them together |
| `/phone <4 số>` · `/phone clear` | Save or clear your default last 4 phone digits |
| `/location` · `/location off` | Save your area (rounded to about 1 km) for distances and maps, or delete it |
| `/check` | Check all your parcels now and match their carriers again (once every 2 minutes). The 🔄 Kiểm tra tất cả button under `/list` does the same |
| `/cancel` | Cancel a pending question (phone digits, name, remove, list selection); every question also has a ↩ Hủy button |

- **Phone digits:** J&T and GHN only show tracking with the last 4 digits of the recipient's phone. Save them once with `/phone 1234`, or give them per parcel with `/track <mã> 1234`.
- **Automatic detection:** if a code matches several carriers, `/list` shows "Đang xác định hãng" until one of them has data; the update message then names the carrier. Use `/track <mã> <hãng>` to force a carrier.
- **Link-only carriers:** codes from YunExpress, GHTK, Viettel Post, VNPost and LEX VN get an official tracking link plus a 17TRACK link; they are not tracked. BEST Express and SF Express are the same unless `SEVENTEEN_TRACK_KEY` is set, in which case they are tracked through the 17TRACK API.
- **15-digit numbers** are tracked as Cainiao. A number that turns out to be an order number never gets data and stops after 7 days.
- **Hidden codes:** tracking codes and order numbers in bot messages are blurred (Telegram spoiler); tap to reveal.
- **Progress:** `/list`, digests and updates show how far a parcel has come (` · 80%` and a bar) from its latest status: 10% order created, 30% picked up, 50% at a hub, 60% cleared customs, 80% at the delivery post office, 95% out for delivery, 100% delivered. SPX uses its status codes, other carriers use status keywords; a carrier module can override this with `progress=`. Delivered parcels show `100%` without the bar.
- **Buttons:** update messages and add replies carry ✏️ Đổi tên (rename), 📜 Hành trình (history), 🔄 Kiểm tra (check now, once every 5 minutes per parcel), 🗑 Xóa (remove after confirming), 📤 Chia sẻ (share link), 🗺 Bản đồ (map picture, see *Maps and distance*) and 🔗 Tra cứu ↗ (tracking page). Taps edit the same message. `/list` and digests show numbered buttons that open a parcel card; `/list` shows 5 parcels per page with ⬅️/➡️.
- **Sound:** update messages arrive silently unless a parcel is out for delivery, delivered or returned; quiet hours keep everything silent.
- **Share links:** 📤 Chia sẻ creates a `t.me/<bot>?start=s_…` link. Another allowed user who opens it can add the same parcel (code and name, not your phone digits) to their own list.
- **Tidy chat:** questions that need a second message (phone digits, a parcel name, `/remove` confirmation) are deleted together with your answer once handled. Telegram only lets bots delete messages younger than 48 hours.
- **Quiet hours:** between 22:00 and 07:00 updates still arrive, but silently.

### Screenshots

Send a screenshot of an order (the shop app's shipping details screen works best). The bot reads the shipping code, carrier and product name with Claude Code on this PC, adds the parcel with the product name as its label, and replies. Screenshots are processed in memory and never saved. Claude Code must stay installed and logged in; each screenshot counts toward your Claude plan's usage limits and takes about 10–30 seconds. If the screenshot only shows an order number, the bot asks for the shipping details screen instead.

**Reading screenshots with agy (Gemini) instead.** Set `VISION_ENGINE=agy` and `VISION_TIMEOUT_SECONDS=150` in `.env`, install the OCR proxy task once with `powershell -ExecutionPolicy Bypass -File scripts\install-proxy-task.ps1`, then restart the bot. The bot sends each screenshot to the proxy on this PC (`127.0.0.1:8765`, nothing else can reach it). The proxy saves the image in a new temporary folder, runs `agy` with `AGY_MODEL` in sandboxed plan mode with only that folder added, deletes the folder and hands the result back. If agy tries to use anything other than opening that file (for example because text in the screenshot tells it to), the reply is thrown away and logged as `error=blocked`. When a code in the reply matches no carrier, or has the wrong length for its carrier (SPX codes have 17 characters), the bot asks the proxy to read the screenshot once more and keeps the better read, so those screenshots take about twice as long. agy must stay installed and logged in. Gemini 3.8 Flash often needs 40–100 seconds; when it fails or times out the proxy tries `AGY_FALLBACK_MODEL` once. Flash models sometimes drop a digit from a long run of the same digit, so glance at the code in the reply. Keep agy's own allow list (`%USERPROFILE%\.gemini\antigravity-cli\settings.json`) free of commands you would not want a screenshot to trigger.

### Daily digests

At 07:00, 12:00, 19:00 and 22:00 every allowed user who has parcels gets one summary message with sound. It lists active parcels with 🆕 on the ones that changed since the previous digest, and parcels that were delivered, returned or stopped since then are shown once. Instant updates still arrive as before. To change the times, set `DIGEST_TIMES` in `.env` (for example `DIGEST_TIMES=08:00,20:00`, or leave it empty to turn digests off) and restart the bot. A digest time missed while the PC was off is skipped; the next digest covers everything since the last one.

### Maps and distance

Send `/location` once and tap **📍 Gửi vị trí** on your phone. Telegram Desktop cannot share a location: paste coordinates such as `21.03, 105.85` instead (in Google Maps, right-click your area and click the coordinates to copy them), or a Google Maps link that contains coordinates; short `maps.app.goo.gl` links do not work. The bot deletes the pasted message. The bot keeps only your area, rounded to about 1 km; `/location off` deletes it. Cards and update messages then end with the parcel's current hub and the straight-line distance to your area, for example `📍 Kho Thanh Tri · cách bạn ~10 km (đường chim bay)`. Tap **🗺 Bản đồ** for a map picture with the hub and your area (once a minute per parcel; without a saved area the bot asks for it first). When a parcel reaches a new hub, its map follows the update message silently.

SPX hubs are read from the status text; other carriers show the location they report, and parcels without one get no map. Hubs are looked up on Photon and drawn on CARTO map tiles, both built on OpenStreetMap data (© OpenStreetMap contributors © CARTO); your location is never sent to them. Set `MAPS_ENABLED=false` in `.env` and restart the bot to turn maps off.

## Carrier stickers

Send a sticker from any Telegram pack to the bot, then reply to that sticker with `/sticker spx` (admin only; any carrier code works, and `/sticker xyz` lists them). The bot then sends that sticker silently just before each SPX update message. `/sticker` lists carriers that have a sticker; `/sticker spx off` removes it. If the pack owner deletes the sticker, the bot logs it once and skips it until the next restart.

## Fixing a carrier while the bot runs

Each carrier is one file in `src/vn_parcel_bot/carriers/modules/` (its code rules, name, link, notes, example codes and tracking client). Edit and save the file: within about a minute the bot loads the new version, checks every carrier's example codes and switches over without a restart (log line `carrier module reloaded code=<name>`). If the new version fails to load or breaks another carrier's examples, the bot keeps the last working version, logs `carrier module rejected` and sends the admin `⚠️ Module <name> lỗi, vẫn dùng bản cũ: <error>` once. Adding a file adds a carrier. Changes to any other file still need a restart.

## Adding family and friends

1. They open your bot and send `/start`; the bot replies with their numeric ID.
2. They forward that ID to you.
3. You send `/allow <id> <tên>`. They get a welcome message.

Admin commands (`/hozk` lists them; only the admin sees them in the command menu): `/allow <id> [tên]`, `/revoke <id>`, `/users`, `/health`, `/sticker <hãng> [off]`.

## Operations

| Task | Command |
|---|---|
| Status | `powershell -ExecutionPolicy Bypass -File scripts\status-bot.ps1` |
| Stop | `Stop-ScheduledTask "VN Parcel Bot"` |
| Start | `Start-ScheduledTask "VN Parcel Bot"` |
| Restart | Stop, then Start |
| OCR proxy (`agy` engine) | `Stop-ScheduledTask` / `Start-ScheduledTask "VN Parcel OCR Proxy"`; health at `http://127.0.0.1:8765/health` |
| Update | `git pull`, `.\.venv\Scripts\python -m pip install -e .`, then restart the task |
| Logs | `logs\bot.log` (rotates at 1 MB, 5 files kept); startup problems in `logs\startup-error.log`; OCR proxy in `logs\agy-proxy.log` |
| Database | `data\bot.sqlite3` |
| Reset everything | Stop the task, delete `data\bot.sqlite3`, start the task |

## Troubleshooting

| Symptom | Likely cause | Check | Fix |
|---|---|---|---|
| Bot never replies | Task not running or crashed | `scripts\status-bot.ps1`; `logs\startup-error.log` | Fix `.env`; `Start-ScheduledTask "VN Parcel Bot"` |
| `startup-error.log`: Invalid configuration | Missing or invalid `.env` value | The listed variables | Edit `.env`, restart the task |
| Log: `NetworkError` / `TimedOut` repeatedly | Telegram blocked or internet down | `probe_carriers.py telegram` | Set `TELEGRAM_PROXY_URL`, restart |
| Log: `another bot instance is polling` | The same token runs elsewhere | Other PCs, a foreground run | Stop the other copy |
| Log: `another instance is running; exiting` | Normal when a second copy starts | – | Nothing |
| Admin gets a carrier alert | Carrier site changed or is blocking | `probe_carriers.py carriers --parse` | See `BUILD_PLAN.md` Appendix A |
| J&T/GHN parcel stays without data | Wrong 4 digits, or not scanned yet | Try the carrier's website with the same digits | `/remove`, then `/track <mã> <4 số đúng>` |
| `/list` shows "Đang xác định hãng" for days | No candidate carrier has data yet | `/status <số>` | Wait, or `/remove` then `/track <mã> [4 số] <hãng>` |
| Updates arrive late | PC was asleep or off | Power settings | Sleep = Never when plugged in |
| No sound at night | Quiet hours | `QUIET_HOURS` in `.env` | Change it or set it empty |
| Screenshot replies with an error (`VISION_ENGINE=agy`) | OCR proxy not running, agy logged out, or Gemini busy | `logs\bot.log` (`vision agy error=`), `logs\agy-proxy.log` | `Start-ScheduledTask "VN Parcel OCR Proxy"`; run `agy` once to log in; `error=blocked` means the screenshot's text tried to steer agy |
| Family member gets 🔒 | Not allowlisted or revoked | `/users` | `/allow <id> <tên>` |
| `ZoneInfoNotFoundError` | `tzdata` missing | `pip show tzdata` | `pip install -e .` |

## Maintenance

- Once a month, run `.\.venv\Scripts\python scripts\probe_carriers.py carriers --parse` with a few current codes.
- On repeated carrier alerts, follow the maintenance prompt in `BUILD_PLAN.md` Appendix A.

## Privacy

The bot stores Telegram IDs and display names of allowed users, tracking codes, tracking events, optional parcel labels, and only the **last 4 digits** of phone numbers, all in `data\bot.sqlite3` on this PC. Delivered, returned, expired and stale parcels are deleted 30 days after their last update. Logs contain counts and masked codes only, never the bot token or message contents. With maps, your area is stored rounded to about 1 km and never logged; only hub names go to Photon, and map squares from CARTO are kept in `data\tiles` for a week.
