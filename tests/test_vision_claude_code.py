import asyncio
import base64
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from vn_parcel_bot.services.vision import VISION_PROMPT, AnthropicVisionEngine
from vn_parcel_bot.services.vision_claude_code import (
    ClaudeCodeVisionEngine,
    ProcessOutput,
    build_args,
    run_process,
)
from vn_parcel_bot.services.vision_engines import build_vision_engine

RESULT_JSON = json.dumps(
    {
        "tracking_codes": ["SPXVN000000000001"],
        "order_ids": ["250914ABCDEF12"],
        "carrier": "SPX Express",
        "product_names": ["Tai nghe Bluetooth", "Ốp lưng"],
        "phone_last4": "000",
    },
    ensure_ascii=False,
)


def stream(*events: dict) -> bytes:
    return "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events).encode("utf-8")


def ok_output(text: str | None = None) -> ProcessOutput:
    text = text if text is not None else f"```json\n{RESULT_JSON}\n```"
    return ProcessOutput(
        returncode=0,
        stdout=stream(
            {"type": "system", "subtype": "init", "tools": [], "mcp_servers": []},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}},
            {"type": "rate_limit_event"},
            {"type": "result", "subtype": "success", "is_error": False, "result": text},
        ),
        stderr=b"",
    )


def _dir_snapshot(path: str) -> tuple[bool, list[Path]]:
    folder = Path(path)
    return folder.is_dir(), list(folder.iterdir())


def _path_exists(path: str) -> bool:
    return Path(path).exists()


class FakeRunner:
    def __init__(self, output=None, exc=None, delay=0.0):
        self.output = output or ok_output()
        self.exc = exc
        self.delay = delay
        self.calls: list[SimpleNamespace] = []
        self.active = 0
        self.max_active = 0

    async def __call__(self, args, stdin, cwd, time_limit):
        was_dir, entries = _dir_snapshot(cwd)
        self.calls.append(
            SimpleNamespace(
                args=list(args),
                stdin=stdin,
                cwd=cwd,
                timeout=time_limit,
                cwd_was_dir=was_dir,
                cwd_entries=entries,
            )
        )
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            if self.exc is not None:
                raise self.exc
            return self.output
        finally:
            self.active -= 1


@pytest.fixture
def cc_settings(settings, tmp_path):
    exe = tmp_path / "claude.exe"
    exe.write_bytes(b"")
    return replace(
        settings, claude_code_path=str(exe), vision_model="haiku", vision_timeout_seconds=90
    )


def test_not_configured_without_executable(settings, tmp_path):
    for path in (None, str(tmp_path / "missing.exe")):
        engine = ClaudeCodeVisionEngine(replace(settings, claude_code_path=path), FakeRunner())
        assert not engine.is_configured


async def test_missing_executable_returns_not_configured(settings, tmp_path):
    runner = FakeRunner()
    engine = ClaudeCodeVisionEngine(
        replace(settings, claude_code_path=str(tmp_path / "missing.exe")), runner
    )
    result = await engine.analyze_image(b"img")
    assert result.error == "not_configured"
    assert runner.calls == []


async def test_success_parses_last_result_event(cc_settings):
    result = await ClaudeCodeVisionEngine(cc_settings, FakeRunner()).analyze_image(
        b"img", "image/png"
    )
    assert result.error is None
    assert result.tracking_codes == ("SPXVN000000000001",)
    assert result.order_ids == ("250914ABCDEF12",)
    assert result.carrier == "SPX Express"
    assert result.product_name == "Tai nghe Bluetooth +1"
    assert result.phone_last4 is None


async def test_command_line_is_locked_down(cc_settings):
    runner = FakeRunner()
    await ClaudeCodeVisionEngine(cc_settings, runner).analyze_image(b"img")
    call = runner.calls[0]
    assert call.args == build_args(cc_settings.claude_code_path, "haiku")
    assert call.args == [
        cc_settings.claude_code_path,
        "-p",
        "--input-format",
        "stream-json",
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        "haiku",
        "--tools",
        "",
        "--no-session-persistence",
        "--strict-mcp-config",
        "--setting-sources",
        "project",
    ]
    assert call.timeout == 90


async def test_stdin_carries_image_then_prompt(cc_settings):
    runner = FakeRunner()
    await ClaudeCodeVisionEngine(cc_settings, runner).analyze_image(b"png-bytes", "image/png")
    lines = runner.calls[0].stdin.decode("utf-8").splitlines()
    assert len(lines) == 1
    message = json.loads(lines[0])
    assert message["type"] == "user"
    assert message["message"]["role"] == "user"
    image, prompt = message["message"]["content"]
    assert image["source"] == {
        "type": "base64",
        "media_type": "image/png",
        "data": base64.b64encode(b"png-bytes").decode("ascii"),
    }
    assert prompt == {"type": "text", "text": VISION_PROMPT}


async def test_runs_in_empty_temporary_directory_removed_afterwards(cc_settings):
    runner = FakeRunner()
    await ClaudeCodeVisionEngine(cc_settings, runner).analyze_image(b"img")
    call = runner.calls[0]
    assert call.cwd_was_dir
    assert call.cwd_entries == []
    assert not _path_exists(call.cwd)


@pytest.mark.parametrize(
    "output",
    [
        ProcessOutput(
            1,
            stream({"type": "result", "subtype": "success", "is_error": False, "result": "{}"}),
            b"boom",
        ),
        ProcessOutput(
            0,
            stream(
                {
                    "type": "result",
                    "subtype": "error_during_execution",
                    "is_error": True,
                    "result": "Claude AI usage limit reached",
                }
            ),
            b"",
        ),
        ProcessOutput(0, stream({"type": "system", "subtype": "init"}), b""),
        ProcessOutput(0, b"not json at all\n", b""),
    ],
    ids=["non-zero-exit", "is-error", "no-result-event", "garbage"],
)
async def test_cli_errors(cc_settings, output):
    result = await ClaudeCodeVisionEngine(cc_settings, FakeRunner(output)).analyze_image(b"img")
    assert result.error == "cli_error"


async def test_empty_result_text_is_invalid(cc_settings):
    output = ProcessOutput(
        0, stream({"type": "result", "subtype": "success", "is_error": False, "result": "  "}), b""
    )
    result = await ClaudeCodeVisionEngine(cc_settings, FakeRunner(output)).analyze_image(b"img")
    assert result.error == "invalid_response"


async def test_timeout(cc_settings):
    engine = ClaudeCodeVisionEngine(cc_settings, FakeRunner(exc=TimeoutError()))
    assert (await engine.analyze_image(b"img")).error == "timeout"


async def test_start_failure_is_not_configured(cc_settings):
    engine = ClaudeCodeVisionEngine(cc_settings, FakeRunner(exc=FileNotFoundError("claude")))
    assert (await engine.analyze_image(b"img")).error == "not_configured"


async def test_calls_are_serialised(cc_settings):
    runner = FakeRunner(delay=0.05)
    engine = ClaudeCodeVisionEngine(cc_settings, runner)
    await asyncio.gather(engine.analyze_image(b"a"), engine.analyze_image(b"b"))
    assert len(runner.calls) == 2
    assert runner.max_active == 1


async def test_logs_hold_no_model_text_or_stderr(cc_settings, caplog):
    caplog.set_level("DEBUG")
    await ClaudeCodeVisionEngine(cc_settings, FakeRunner()).analyze_image(b"img")
    failing = ProcessOutput(
        1, stream({"type": "result", "is_error": True, "result": RESULT_JSON}), b"stderr-secret"
    )
    await ClaudeCodeVisionEngine(cc_settings, FakeRunner(failing)).analyze_image(b"img")
    assert "SPXVN000000000001" not in caplog.text
    assert "Tai nghe" not in caplog.text
    assert "stderr-secret" not in caplog.text


async def test_run_process_passes_stdin_and_returns_output(tmp_path):
    output = await run_process(
        [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read().upper())"],
        b"hello",
        str(tmp_path),
        30,
    )
    assert output.returncode == 0
    assert output.stdout == b"HELLO"


async def test_run_process_kills_on_timeout(tmp_path):
    with pytest.raises(TimeoutError):
        await run_process(
            [sys.executable, "-c", "import time; time.sleep(30)"], b"", str(tmp_path), 0.5
        )


def test_build_vision_engine_picks_engine(settings, cc_settings):
    assert isinstance(build_vision_engine(cc_settings, None), ClaudeCodeVisionEngine)
    api = replace(settings, vision_engine="api")
    assert isinstance(build_vision_engine(api, None), AnthropicVisionEngine)
