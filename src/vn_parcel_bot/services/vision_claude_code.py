import asyncio
import json
import logging
import subprocess
import sys
import tempfile
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vn_parcel_bot.config import Settings
from vn_parcel_bot.services.vision import VisionResult, image_content, parse_vision_text

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessOutput:
    returncode: int
    stdout: bytes
    stderr: bytes


Runner = Callable[[Sequence[str], bytes, str, float], Awaitable[ProcessOutput]]


async def run_process(
    args: Sequence[str], stdin: bytes, cwd: str, time_limit: float
) -> ProcessOutput:
    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(stdin), timeout=time_limit)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise
    returncode = process.returncode if process.returncode is not None else -1
    return ProcessOutput(returncode, stdout, stderr)


def build_args(executable: str, model: str) -> list[str]:
    return [
        executable,
        "-p",
        "--input-format",
        "stream-json",
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        model,
        "--tools",
        "",
        "--no-session-persistence",
        "--strict-mcp-config",
        "--setting-sources",
        "project",
    ]


def build_stdin(image_bytes: bytes, media_type: str) -> bytes:
    message = {
        "type": "user",
        "message": {"role": "user", "content": image_content(image_bytes, media_type)},
    }
    return (json.dumps(message) + "\n").encode("utf-8")


def last_result_event(stdout: bytes) -> dict[str, Any] | None:
    result = None
    for line in stdout.decode("utf-8", "replace").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            result = event
    return result


class ClaudeCodeVisionEngine:
    def __init__(self, settings: Settings, runner: Runner = run_process) -> None:
        self._settings = settings
        self._runner = runner
        self._lock = asyncio.Lock()

    @property
    def is_configured(self) -> bool:
        path = self._settings.claude_code_path
        return bool(path) and Path(path).is_file()

    async def analyze_image(
        self, image_bytes: bytes, media_type: str = "image/jpeg"
    ) -> VisionResult:
        if not self.is_configured:
            return VisionResult(error="not_configured")
        args = build_args(self._settings.claude_code_path or "", self._settings.vision_model)
        stdin = build_stdin(image_bytes, media_type)
        async with self._lock:
            started = time.monotonic()
            with tempfile.TemporaryDirectory(
                prefix="vn-parcel-vision-", ignore_cleanup_errors=True
            ) as workdir:
                try:
                    output = await self._runner(
                        args, stdin, workdir, self._settings.vision_timeout_seconds
                    )
                except TimeoutError:
                    log.warning(
                        "vision claude_code error=timeout duration=%.1fs",
                        time.monotonic() - started,
                    )
                    return VisionResult(error="timeout")
                except OSError as exc:
                    log.warning(
                        "vision claude_code error=not_configured type=%s", type(exc).__name__
                    )
                    return VisionResult(error="not_configured")
            elapsed = time.monotonic() - started
        event = last_result_event(output.stdout)
        subtype = event.get("subtype") if event else None
        if output.returncode != 0 or event is None or event.get("is_error"):
            log.warning(
                "vision claude_code error=cli_error exit=%s subtype=%s duration=%.1fs "
                "stderr_len=%d",
                output.returncode,
                subtype,
                elapsed,
                len(output.stderr),
            )
            return VisionResult(error="cli_error")
        text = event.get("result")
        if not isinstance(text, str) or not text.strip():
            log.warning("vision claude_code error=invalid_response duration=%.1fs", elapsed)
            return VisionResult(error="invalid_response")
        log.info("vision claude_code ok duration=%.1fs", elapsed)
        return parse_vision_text(text)
