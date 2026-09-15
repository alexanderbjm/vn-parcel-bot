#!/usr/bin/env python3
"""Standard Model Context Protocol (MCP) Server for VN Parcel Tracking.

Allows Claude Code, Cursor, Codex, and other MCP clients to query order tracking
via native tool calls over stdio without dealing with bot protection or CAPTCHAs.

Add to Claude Code settings (`~/.claude/settings.json`):
```json
"mcpServers": {
  "vn-parcel-bridge": {
    "command": "C:\\Users\\hozkg\\projects\\vn-parcel-bot\\.venv\\Scripts\\python.exe",
    "args": [
      "C:\\Users\\hozkg\\projects\\vn-parcel-bot\\scripts\\mcp_server.py"
    ]
  }
}
```
"""

import asyncio
import json
import sys
from pathlib import Path

# Ensure vn_parcel_bot package and scripts are on sys.path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))
sys.path.insert(0, str(repo_root))

from scripts.query_order import query_tracking  # noqa: E402

TOOLS = [
    {
        "name": "track_parcel",
        "description": (
            "Check real-time parcel tracking status and milestone history for Vietnamese "
            "and cross-border carriers (SPX, J&T, Cainiao, BEST Express, Viettel Post, "
            "VNPost, GHN, Ninja Van, GHTK, SF Express). Automatically resolves through "
            "local database, carrier APIs, and stealth anti-bot solvers."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": (
                        "The parcel tracking code (e.g., SPXVN062253986319, 841000072647, "
                        "JNTX..., LP...)."
                    ),
                },
                "phone": {
                    "type": "string",
                    "description": (
                        "Optional last 4 digits of recipient's phone number (required for "
                        "J&T Express domestic and GHN)."
                    ),
                },
                "stealth": {
                    "type": "boolean",
                    "description": (
                        "Set to true to launch the Playwright stealth solver for carriers "
                        "with bot auth / slide captchas (like BEST Express)."
                    ),
                },
            },
            "required": ["code"],
        },
    }
]


async def handle_request(req: dict) -> dict | None:
    method = req.get("method")
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "vn-parcel-bridge", "version": "1.0.0"},
            },
        }
    elif method == "notifications/initialized":
        return None
    elif method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    elif method == "tools/call":
        params = req.get("params", {})
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if tool_name == "track_parcel":
            code = str(arguments.get("code", "")).strip()
            phone = arguments.get("phone")
            stealth = bool(arguments.get("stealth", False))

            result = await query_tracking(code, phone_last4=phone, stealth=stealth)
            text_result = json.dumps(result, ensure_ascii=False, indent=2)

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": text_result}],
                    "isError": not result.get("found", False),
                },
            }
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Tool not found: {tool_name}"},
            }
    else:
        if req_id is not None:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
        return None


async def main() -> None:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    loop = asyncio.get_running_loop()

    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        resp = await handle_request(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    asyncio.run(main())
