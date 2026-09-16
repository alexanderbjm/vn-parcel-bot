import asyncio
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from vn_parcel_bot.config import Settings
from vn_parcel_bot.constants import SECRET_ENV_PREFIXES
from vn_parcel_bot.services.vision import (
    SUPPORTED_MEDIA_TYPES,
    VisionResult,
    doubtful_codes,
    parse_vision_text,
    tool_file_prompt,
)
from vn_parcel_bot.services.vision_claude_code import Runner, run_process

log = logging.getLogger(__name__)

IMAGE_NAME = "screenshot"
_SUFFIXES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def image_filename(media_type: str) -> str:
    if media_type not in SUPPORTED_MEDIA_TYPES:
        media_type = "image/jpeg"
    return IMAGE_NAME + _SUFFIXES[media_type]


def build_args(executable: str, model: str) -> list[str]:
    """The prompt goes on stdin, not after ``-p``.

    Passing the query as a ``-p`` argument makes cmdc print the answer as plain prose and skip
    the ``--output-format json`` stream entirely, so there is no result frame to read.
    """
    return [
        executable,
        "-p",
        "--output-format",
        "json",
        "--model",
        model,
        "--no-skills",
        "--skip-onboarding",
    ]


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


def cmdc_environment() -> dict[str, str]:
    """This process's environment without the bot's secrets.

    cmdc authenticates from its own login, so the bot token and the 17TRACK key have no business
    in its process. The bot loads .env into os.environ, so without this the screenshot run would
    inherit both.
    """
    return {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(SECRET_ENV_PREFIXES)
    }


class CmdcVisionEngine:
    """Reads screenshots with the Command Code CLI (``cmdc -p``) already logged in on this PC.

    cmdc has no streamed-image input, so the screenshot is written into a temporary directory and
    the agent is told to open it with its own read_file tool. A headless run denies file writes and
    shell commands unless ``--yolo`` is passed, which is what keeps text inside a screenshot from
    steering the run, so that flag is deliberately absent here.
    """

    def __init__(self, settings: Settings, runner: Runner = run_process) -> None:
        self._settings = settings
        self._runner = runner
        self._lock = asyncio.Lock()

    @property
    def is_configured(self) -> bool:
        path = self._settings.cmdc_path
        return bool(path) and Path(path).is_file()

    async def analyze_image(
        self, image_bytes: bytes, media_type: str = "image/jpeg"
    ) -> VisionResult:
        if not self.is_configured:
            return VisionResult(error="not_configured")
        first = await self._read(image_bytes, media_type, reread=False)
        doubtful = doubtful_codes(first)
        if first.error is not None or doubtful == 0:
            return first
        log.info("vision cmdc reread doubtful_codes=%d", doubtful)
        second = await self._read(image_bytes, media_type, reread=True)
        if (
            second.error is None
            and len(second.tracking_codes) >= len(first.tracking_codes)
            and doubtful_codes(second) <= doubtful
        ):
            log.info("vision cmdc reread used doubtful_codes=%d", doubtful_codes(second))
            return second
        log.info("vision cmdc reread kept the first read")
        return first

    async def _read(self, image_bytes: bytes, media_type: str, *, reread: bool) -> VisionResult:
        name = image_filename(media_type)
        prompt = tool_file_prompt("read_file", name, reread=reread)
        args = build_args(self._settings.cmdc_path or "", self._settings.cmdc_model)
        async with self._lock:
            started = time.monotonic()
            # Everything that can fail before a reply is parsed -- making the temporary folder,
            # writing the screenshot into it, starting the CLI -- is inside this try, so
            # analyze_image always returns a VisionResult rather than letting an OSError escape
            # to the caller.
            try:
                with tempfile.TemporaryDirectory(
                    prefix="vn-parcel-vision-", ignore_cleanup_errors=True
                ) as workdir:
                    (Path(workdir) / name).write_bytes(image_bytes)
                    output = await self._runner(
                        args,
                        prompt.encode("utf-8"),
                        workdir,
                        self._settings.vision_timeout_seconds,
                        cmdc_environment(),
                    )
            except TimeoutError:
                log.warning("vision cmdc error=timeout duration=%.1fs", time.monotonic() - started)
                return VisionResult(error="timeout")
            except FileNotFoundError as exc:
                log.warning("vision cmdc error=not_configured type=%s", type(exc).__name__)
                return VisionResult(error="not_configured")
            except OSError as exc:
                log.warning("vision cmdc error=cli_error stage=setup type=%s", type(exc).__name__)
                return VisionResult(error="cli_error")
            elapsed = time.monotonic() - started
        event = last_result_event(output.stdout)
        subtype = event.get("subtype") if event else None
        if output.returncode != 0 or subtype != "success":
            log.warning(
                "vision cmdc error=cli_error exit=%s subtype=%s duration=%.1fs stderr_len=%d",
                output.returncode,
                subtype,
                elapsed,
                len(output.stderr),
            )
            return VisionResult(error="cli_error")
        text = event.get("finalText")
        if not isinstance(text, str) or not text.strip():
            log.warning("vision cmdc error=invalid_response duration=%.1fs", elapsed)
            return VisionResult(error="invalid_response")
        log.info("vision cmdc ok duration=%.1fs", elapsed)
        return parse_vision_text(text)
