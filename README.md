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
   | `POLL_INTERVAL_MINUTES` | no | `20` | Minutes between checks (5–240) |
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
   | `VISION_ENGINE` | no | `claude_code` | `claude_code` reads screenshots with Claude Code on this PC (your Claude plan); `api` uses Anthropic API credit |
   | `CLAUDE_CODE_PATH` | no | found automatically | Path to `claude.exe` if it is not on `PATH` or in `%USERPROFILE%\.local\bin` |
   | `VISION_MODEL` | no | `sonnet` | Claude Code model for screenshots (Haiku misread long codes) |
   | `VISION_TIMEOUT_SECONDS` | no | `90` | Seconds to wait for one screenshot (10..300) |
   | `ANTHROPIC_API_KEY` | no | – | `api` engine only |
   | `ANTHROPIC_MODEL` | no | `claude-haiku-4-5-20251001` | `api` engine only |
   | `ANTHROPIC_WORKSPACE_ID` | no | – | `api` engine only, for keys not scoped to a workspace |

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
| `/label <mã hoặc số> <tên>` | Name a parcel (no name clears it) |
| `/remove <mã hoặc số>` | Stop tracking |
| `/phone <4 số>` · `/phone clear` | Save or clear your default last 4 phone digits |
| `/check` | Check your parcels now (once every 5 minutes) |
| `/cancel` | Cancel a pending phone-digit question |

- **Phone digits:** J&T and GHN only show tracking with the last 4 digits of the recipient's phone. Save them once with `/phone 1234`, or give them per parcel with `/track <mã> 1234`.
- **Automatic detection:** if a code matches several carriers, `/list` shows "Đang xác định hãng" until one of them has data; the update message then names the carrier. Use `/track <mã> <hãng>` to force a carrier.
- **Link-only carriers:** codes from BEST Express, YunExpress, GHTK, Viettel Post, VNPost, LEX VN and SF Express get an official tracking link plus a 17TRACK link; they are not tracked.
- **Quiet hours:** between 22:00 and 07:00 updates still arrive, but silently.

### Screenshots

Send a screenshot of an order (the shop app's shipping details screen works best). The bot reads the shipping code, carrier and product name with Claude Code on this PC, adds the parcel with the product name as its label, and replies. Screenshots are processed in memory and never saved. Claude Code must stay installed and logged in; each screenshot counts toward your Claude plan's usage limits and takes about 10–30 seconds. If the screenshot only shows an order number, the bot asks for the shipping details screen instead.

### Daily digests

At 07:00, 12:00, 19:00 and 22:00 every allowed user who has parcels gets one summary message with sound. It lists active parcels with 🆕 on the ones that changed since the previous digest, and parcels that were delivered, returned or stopped since then are shown once. Instant updates still arrive as before. To change the times, set `DIGEST_TIMES` in `.env` (for example `DIGEST_TIMES=08:00,20:00`, or leave it empty to turn digests off) and restart the bot. A digest time missed while the PC was off is skipped; the next digest covers everything since the last one.

## Adding family and friends

1. They open your bot and send `/start`; the bot replies with their numeric ID.
2. They forward that ID to you.
3. You send `/allow <id> <tên>`. They get a welcome message.

Admin commands: `/allow <id> [tên]`, `/revoke <id>`, `/users`, `/health`.

## Operations

| Task | Command |
|---|---|
| Status | `powershell -ExecutionPolicy Bypass -File scripts\status-bot.ps1` |
| Stop | `Stop-ScheduledTask "VN Parcel Bot"` |
| Start | `Start-ScheduledTask "VN Parcel Bot"` |
| Restart | Stop, then Start |
| Update | `git pull`, `.\.venv\Scripts\python -m pip install -e .`, then restart the task |
| Logs | `logs\bot.log` (rotates at 1 MB, 5 files kept); startup problems in `logs\startup-error.log` |
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
| Family member gets 🔒 | Not allowlisted or revoked | `/users` | `/allow <id> <tên>` |
| `ZoneInfoNotFoundError` | `tzdata` missing | `pip show tzdata` | `pip install -e .` |

## Maintenance

- Once a month, run `.\.venv\Scripts\python scripts\probe_carriers.py carriers --parse` with a few current codes.
- On repeated carrier alerts, follow the maintenance prompt in `BUILD_PLAN.md` Appendix A.

## Privacy

The bot stores Telegram IDs and display names of allowed users, tracking codes, tracking events, optional parcel labels, and only the **last 4 digits** of phone numbers, all in `data\bot.sqlite3` on this PC. Delivered, returned, expired and stale parcels are deleted 30 days after their last update. Logs contain counts and masked codes only, never the bot token or message contents.
