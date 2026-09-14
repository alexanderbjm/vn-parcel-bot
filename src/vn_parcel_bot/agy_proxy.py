"""Local screenshot proxy: bot -> this proxy -> agy CLI (Gemini) -> this proxy -> bot.

Run with ``python -m vn_parcel_bot.agy_proxy`` (the "VN Parcel OCR Proxy" scheduled task). It
listens only on the loopback address from AGY_PROXY_URL, copies each image into its own temporary
folder, lets agy open that folder in sandboxed plan mode and hands agy's reply back to the bot.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Protocol

from dotenv import dotenv_values

from vn_parcel_bot.config import AgyProxyConfig, ConfigError
from vn_parcel_bot.constants import VISION_MAX_IMAGE_BYTES
from vn_parcel_bot.logging_setup import LOG_FORMAT
from vn_parcel_bot.services.vision import file_prompt
from vn_parcel_bot.services.vision_claude_code import ProcessOutput

log = logging.getLogger(__name__)

READ_PATH = "/read"
HEALTH_PATH = "/health"
PROXY_HEADER = "X-VN-Parcel-Proxy"
IMAGE_SUFFIXES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
ALLOWED_TOOLS = frozenset({"view_file"})
PROCESS_GRACE_SECONDS = 15
_SECRET_ENV_PREFIXES = ("ANTHROPIC_", "TELEGRAM_", "SEVENTEEN_TRACK_")

SyncRunner = Callable[[Sequence[str], str, float, Mapping[str, str]], ProcessOutput]


@dataclass(frozen=True)
class ReadResult:
    text: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class AgyRun:
    status: str | None
    response: str
    tools: tuple[str, ...]
    denied: tuple[str, ...]


def run_agy(
    args: Sequence[str], cwd: str, time_limit: float, env: Mapping[str, str]
) -> ProcessOutput:
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argument list, no shell
            list(args),
            cwd=cwd,
            env=dict(env),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=time_limit,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError from exc
    return ProcessOutput(completed.returncode, completed.stdout, completed.stderr)


def agy_environment() -> dict[str, str]:
    """This process's environment without bot secrets (agy only needs its own Google login)."""
    return {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(_SECRET_ENV_PREFIXES)
    }


def build_agy_args(
    executable: str, model: str, workdir: str, image_path: str, timeout_seconds: int
) -> list[str]:
    return [
        executable,
        "--mode",
        "plan",
        "--sandbox",
        "--model",
        model,
        "--add-dir",
        workdir,
        "--output-format",
        "stream-json",
        "--print-timeout",
        f"{timeout_seconds}s",
        f"-p={file_prompt(image_path)}",
    ]


def parse_agy_stream(stdout: bytes) -> AgyRun:
    status: str | None = None
    response = ""
    tools: list[str] = []
    denied: list[str] = []
    for line in stdout.decode("utf-8", "replace").splitlines():
        try:
            event: Any = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("event") == "step_update":
            step = event.get("step_update")
            if isinstance(step, dict) and step.get("step_type") == "tool":
                name = step.get("tool_name")
                if isinstance(name, str) and name not in tools:
                    tools.append(name)
        elif event.get("event") == "result" and isinstance(event.get("result"), dict):
            result = event["result"]
            status = result.get("status") if isinstance(result.get("status"), str) else None
            response = result.get("response") if isinstance(result.get("response"), str) else ""
            for item in result.get("denied_actions") or []:
                if isinstance(item, dict) and isinstance(item.get("action"), str):
                    denied.append(item["action"])
    return AgyRun(status, response, tuple(tools), tuple(denied))


class AgyReader:
    """Runs agy on one image at a time; falls back to a second model when the first one fails."""

    def __init__(self, config: AgyProxyConfig, runner: SyncRunner = run_agy) -> None:
        self._config = config
        self._runner = runner
        self._lock = threading.Lock()

    @property
    def is_configured(self) -> bool:
        path = self._config.agy_path
        return bool(path) and Path(path).is_file()

    @property
    def model(self) -> str:
        return self._config.model

    def read(self, image_bytes: bytes, media_type: str) -> ReadResult:
        if not self.is_configured:
            log.warning("agy error=not_configured")
            return ReadResult(error="not_configured")
        with self._lock:
            workdir = tempfile.mkdtemp(prefix="vn-parcel-agy-")
            try:
                image = Path(workdir) / f"screenshot{IMAGE_SUFFIXES.get(media_type, '.jpg')}"
                image.write_bytes(image_bytes)
                result = self._attempt(self._config.model, workdir, str(image))
                fallback = self._config.fallback_model
                retry = result.error in ("cli_error", "timeout")
                if retry and fallback and fallback != self._config.model:
                    log.warning("agy retry model=%s", fallback)
                    result = self._attempt(fallback, workdir, str(image))
                return result
            finally:
                shutil.rmtree(workdir, ignore_errors=True)

    def _attempt(self, model: str, workdir: str, image_path: str) -> ReadResult:
        timeout = self._config.timeout_seconds
        args = build_agy_args(self._config.agy_path or "", model, workdir, image_path, timeout)
        started = time.monotonic()
        try:
            output = self._runner(args, workdir, timeout + PROCESS_GRACE_SECONDS, agy_environment())
        except TimeoutError:
            log.warning(
                "agy error=timeout model=%s duration=%.1fs", model, time.monotonic() - started
            )
            return ReadResult(error="timeout")
        except OSError as exc:
            log.warning("agy error=not_configured type=%s", type(exc).__name__)
            return ReadResult(error="not_configured")
        elapsed = time.monotonic() - started
        run = parse_agy_stream(output.stdout)
        unexpected = [tool for tool in run.tools if tool not in ALLOWED_TOOLS]
        if unexpected or run.denied:
            # Text inside a screenshot tried to steer agy: throw the whole reply away.
            log.warning(
                "agy error=blocked model=%s tools=%s denied=%s duration=%.1fs",
                model,
                ",".join(unexpected) or "-",
                ",".join(run.denied) or "-",
                elapsed,
            )
            return ReadResult(error="blocked")
        if output.returncode != 0 or run.status != "SUCCESS":
            log.warning(
                "agy error=cli_error model=%s exit=%s status=%s duration=%.1fs stderr_len=%d",
                model,
                output.returncode,
                run.status,
                elapsed,
                len(output.stderr),
            )
            return ReadResult(error="cli_error")
        if not run.response.strip():
            log.warning("agy error=invalid_response model=%s duration=%.1fs", model, elapsed)
            return ReadResult(error="invalid_response")
        log.info("agy ok model=%s duration=%.1fs", model, elapsed)
        return ReadResult(text=run.response)


class Reader(Protocol):
    @property
    def is_configured(self) -> bool: ...

    @property
    def model(self) -> str: ...

    def read(self, image_bytes: bytes, media_type: str) -> ReadResult: ...


def make_handler(reader: Reader) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "vn-parcel-agy-proxy"
        sys_version = ""

        def log_message(self, format: str, *args: Any) -> None:
            log.debug("http %s", format % args)

        def do_GET(self) -> None:
            if self.path != HEALTH_PATH:
                self._send(404, {"error": "not_found"})
                return
            self._send(200, {"ok": True, "agy": reader.is_configured, "model": reader.model})

        def do_POST(self) -> None:
            media_type = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            try:
                length: int | None = int(self.headers.get("Content-Length") or "")
            except ValueError:
                length = None
            refusal = self._refusal(media_type, length)
            if refusal is not None or length is None:
                # Read the upload first: closing a socket with unread data resets the connection
                # on Windows before the client sees the answer.
                self._drain(length)
                status, error = refusal or (411, "length_required")
                self._send(status, {"error": error})
                return
            body = self.rfile.read(length)
            if len(body) != length:
                self._send(400, {"error": "incomplete"})
                return
            result = reader.read(body, media_type)
            payload = {"text": result.text} if result.error is None else {"error": result.error}
            self._send(200, payload)

        def _refusal(self, media_type: str, length: int | None) -> tuple[int, str] | None:
            if self.path != READ_PATH:
                return 404, "not_found"
            # Browsers cannot send the custom header cross-site without a preflight we never
            # answer, so web pages cannot use the proxy.
            if self.headers.get("Origin") is not None or self.headers.get(PROXY_HEADER) != "1":
                return 403, "forbidden"
            if media_type not in IMAGE_SUFFIXES:
                return 415, "unsupported_media_type"
            if length is None:
                return 411, "length_required"
            if length <= 0:
                return 400, "empty"
            if length > VISION_MAX_IMAGE_BYTES:
                return 413, "too_large"
            return None

        def _drain(self, length: int | None) -> None:
            remaining = min(length or 0, 2 * VISION_MAX_IMAGE_BYTES)
            while remaining > 0:
                chunk = self.rfile.read(min(remaining, 65536))
                if not chunk:
                    break
                remaining -= len(chunk)

        def _send(self, status: int, payload: dict[str, Any]) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


def build_server(config: AgyProxyConfig, reader: Reader) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((config.host, config.port), make_handler(reader))
    server.daemon_threads = True
    return server


def setup_proxy_logging(config: AgyProxyConfig) -> None:
    config.log_dir.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        RotatingFileHandler(
            config.log_dir / "agy-proxy.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8"
        )
    ]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(level=config.log_level, format=LOG_FORMAT, handlers=handlers, force=True)


def load_env() -> dict[str, str]:
    """.env values for configuration only; they are never copied into agy's environment."""
    env = {k: v for k, v in dotenv_values(Path.cwd() / ".env").items() if v is not None}
    env.update(os.environ)
    return env


def main() -> int:
    try:
        config = AgyProxyConfig.from_env(load_env())
    except ConfigError as exc:
        if sys.stderr is not None:
            print(exc, file=sys.stderr)
        return 2
    setup_proxy_logging(config)
    reader = AgyReader(config)
    try:
        server = build_server(config, reader)
    except OSError as exc:
        log.warning(
            "cannot listen on %s:%s type=%s (already running?)",
            config.host,
            config.port,
            type(exc).__name__,
        )
        return 0
    log.info(
        "agy proxy listening on %s:%s model=%s fallback=%s agy=%s",
        config.host,
        config.port,
        config.model,
        config.fallback_model or "-",
        "found" if reader.is_configured else "missing",
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
