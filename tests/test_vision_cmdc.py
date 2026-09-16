import asyncio
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from vn_parcel_bot.services.vision import AnthropicVisionEngine, file_prompt, tool_file_prompt
from vn_parcel_bot.services.vision_claude_code import ProcessOutput, run_process
from vn_parcel_bot.services.vision_cmdc import (
    CmdcVisionEngine,
    build_args,
    image_filename,
    last_result_event,
)
from vn_parcel_bot.services.vision_engines import build_vision_engine

RESULT_JSON = json.dumps(
    {
        "tracking_codes": ["SPXVN000000000001"],
        "order_ids": ["250914ABCDEF12"],
        "carrier": "SPX Express",
        "product_names": ["Tai nghe Bluetooth", "Ốp lưng"],
        "phone_last4": "4567",
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
            {"type": "event", "event": {"type": "turn_end", "turnNumber": 2}},
            {
                "type": "result",
                "subtype": "success",
                "stopReason": "end_turn",
                "finalText": text,
            },
        ),
        stderr=b"",
    )


def codes_output(*codes: str) -> ProcessOutput:
    return ok_output(json.dumps({"tracking_codes": list(codes)}))


def _dir_snapshot(path: str) -> tuple[bool, list[str], bytes]:
    folder = Path(path)
    if not folder.is_dir():
        return False, [], b""
    files = [item for item in folder.iterdir() if item.is_file()]
    return True, sorted(item.name for item in files), b"".join(item.read_bytes() for item in files)


def _path_exists(path: str) -> bool:
    return Path(path).exists()


class FakeRunner:
    def __init__(self, outputs=None, exc=None, delay=0.0):
        if outputs is None:
            outputs = [ok_output()]
        elif isinstance(outputs, ProcessOutput):
            outputs = [outputs]
        self.outputs = list(outputs)
        self.exc = exc
        self.delay = delay
        self.calls: list[SimpleNamespace] = []
        self.active = 0
        self.max_active = 0

    async def __call__(self, args, stdin, cwd, time_limit, env=None):
        was_dir, entries, image = _dir_snapshot(cwd)
        self.calls.append(
            SimpleNamespace(
                args=list(args),
                stdin=stdin,
                cwd=cwd,
                timeout=time_limit,
                env=env,
                cwd_was_dir=was_dir,
                cwd_entries=entries,
                image=image,
            )
        )
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            if self.exc is not None:
                raise self.exc
            return self.outputs[min(len(self.calls) - 1, len(self.outputs) - 1)]
        finally:
            self.active -= 1


@pytest.fixture
def cmdc_settings(settings, tmp_path):
    exe = tmp_path / "cmdc.cmd"
    exe.write_bytes(b"")
    return replace(
        settings,
        vision_engine="cmdc",
        cmdc_path=str(exe),
        cmdc_model="qwen/qwen3.8-27b",
        vision_timeout_seconds=90,
    )


def test_not_configured_without_executable(settings, tmp_path):
    for path in (None, str(tmp_path / "missing.cmd")):
        engine = CmdcVisionEngine(replace(settings, cmdc_path=path), FakeRunner())
        assert not engine.is_configured


def test_build_vision_engine_picks_cmdc(settings, cmdc_settings):
    assert isinstance(build_vision_engine(cmdc_settings, None), CmdcVisionEngine)
    api = replace(settings, vision_engine="api")
    assert isinstance(build_vision_engine(api, None), AnthropicVisionEngine)


async def test_missing_executable_returns_not_configured(settings, tmp_path):
    runner = FakeRunner()
    engine = CmdcVisionEngine(replace(settings, cmdc_path=str(tmp_path / "missing.cmd")), runner)
    result = await engine.analyze_image(b"img")
    assert result.error == "not_configured"
    assert runner.calls == []


async def test_success_parses_last_result_event(cmdc_settings):
    result = await CmdcVisionEngine(cmdc_settings, FakeRunner()).analyze_image(b"img", "image/png")
    assert result.error is None
    assert result.tracking_codes == ("SPXVN000000000001",)
    assert result.order_ids == ("250914ABCDEF12",)
    assert result.carrier == "SPX Express"
    assert result.product_name == "Tai nghe Bluetooth +1"
    assert result.phone_last4 == "4567"


async def test_command_line_cannot_write_or_run_anything(cmdc_settings):
    runner = FakeRunner()
    await CmdcVisionEngine(cmdc_settings, runner).analyze_image(b"img")
    call = runner.calls[0]
    assert call.args == build_args(cmdc_settings.cmdc_path, "qwen/qwen3.8-27b")
    assert call.args == [
        cmdc_settings.cmdc_path,
        "-p",
        "--output-format",
        "json",
        "--model",
        "qwen/qwen3.8-27b",
        "--no-skills",
        "--skip-onboarding",
    ]
    # Text inside a screenshot is untrusted, so the run must stay read-only.
    assert "--yolo" not in call.args
    assert "--dangerously-skip-permissions" not in call.args
    assert call.timeout == 90


async def test_prompt_travels_on_stdin_not_argv(cmdc_settings):
    runner = FakeRunner()
    await CmdcVisionEngine(cmdc_settings, runner).analyze_image(b"img", "image/png")
    call = runner.calls[0]
    assert call.stdin.decode("utf-8") == tool_file_prompt("read_file", "screenshot.png")
    assert all("read_file tool" not in arg for arg in call.args)


async def test_writes_the_image_into_a_temporary_directory_removed_afterwards(cmdc_settings):
    runner = FakeRunner()
    await CmdcVisionEngine(cmdc_settings, runner).analyze_image(b"png-bytes", "image/png")
    call = runner.calls[0]
    assert call.cwd_was_dir
    assert call.cwd_entries == ["screenshot.png"]
    assert call.image == b"png-bytes"
    assert not _path_exists(call.cwd)


@pytest.mark.parametrize(
    ("media_type", "expected"),
    [
        ("image/png", "screenshot.png"),
        ("image/jpeg", "screenshot.jpg"),
        ("image/gif", "screenshot.gif"),
        ("image/webp", "screenshot.webp"),
        ("image/tiff", "screenshot.jpg"),
    ],
)
async def test_unknown_media_type_falls_back_to_jpeg(cmdc_settings, media_type, expected):
    runner = FakeRunner()
    await CmdcVisionEngine(cmdc_settings, runner).analyze_image(b"img", media_type)
    prompt = runner.calls[0].stdin.decode("utf-8")
    assert runner.calls[0].cwd_entries == [expected]
    assert image_filename(media_type) == expected
    assert f"open the image file {expected} and use no other tool" in prompt


@pytest.mark.parametrize(
    "output",
    [
        ProcessOutput(
            1, stream({"type": "result", "subtype": "success", "finalText": "{}"}), b"boom"
        ),
        ProcessOutput(0, stream({"type": "result", "subtype": "error", "finalText": ""}), b""),
        ProcessOutput(
            0, stream({"type": "result", "subtype": "max_turns", "finalText": "{}"}), b""
        ),
        ProcessOutput(0, stream({"type": "event", "event": {"type": "turn_end"}}), b""),
        ProcessOutput(0, b"not json at all\n", b""),
    ],
    ids=["non-zero-exit", "subtype-error", "max-turns", "no-result-event", "garbage"],
)
async def test_cli_errors(cmdc_settings, output):
    result = await CmdcVisionEngine(cmdc_settings, FakeRunner(output)).analyze_image(b"img")
    assert result.error == "cli_error"


async def test_prose_instead_of_a_result_frame_is_an_error(cmdc_settings):
    # cmdc prints plain prose when the query is passed as a -p argument; that must not parse.
    output = ProcessOutput(0, b"I read the file but cannot see it.\n", b"")
    result = await CmdcVisionEngine(cmdc_settings, FakeRunner(output)).analyze_image(b"img")
    assert result.error == "cli_error"
    assert last_result_event(output.stdout) is None


async def test_empty_result_text_is_invalid(cmdc_settings):
    output = ProcessOutput(
        0, stream({"type": "result", "subtype": "success", "finalText": "  "}), b""
    )
    result = await CmdcVisionEngine(cmdc_settings, FakeRunner(output)).analyze_image(b"img")
    assert result.error == "invalid_response"


async def test_timeout(cmdc_settings):
    engine = CmdcVisionEngine(cmdc_settings, FakeRunner(exc=TimeoutError()))
    assert (await engine.analyze_image(b"img")).error == "timeout"


async def test_start_failure_is_not_configured(cmdc_settings):
    engine = CmdcVisionEngine(cmdc_settings, FakeRunner(exc=FileNotFoundError("cmdc")))
    assert (await engine.analyze_image(b"img")).error == "not_configured"


async def test_calls_are_serialised(cmdc_settings):
    runner = FakeRunner(delay=0.05)
    engine = CmdcVisionEngine(cmdc_settings, runner)
    await asyncio.gather(engine.analyze_image(b"a"), engine.analyze_image(b"b"))
    assert len(runner.calls) == 2
    assert runner.max_active == 1


async def test_well_formed_codes_are_read_once(cmdc_settings):
    runner = FakeRunner(codes_output("SPXVN000000000001"))
    result = await CmdcVisionEngine(cmdc_settings, runner).analyze_image(b"img")
    assert result.tracking_codes == ("SPXVN000000000001",)
    assert len(runner.calls) == 1


async def test_rereads_once_when_a_code_has_the_wrong_length(cmdc_settings, caplog):
    caplog.set_level("INFO")
    runner = FakeRunner([codes_output("SPXVN00000000001"), codes_output("SPXVN000000000001")])
    result = await CmdcVisionEngine(cmdc_settings, runner).analyze_image(b"img")
    assert result.tracking_codes == ("SPXVN000000000001",)
    assert len(runner.calls) == 2
    assert "reread" not in runner.calls[0].stdin.decode("utf-8")
    assert "count the characters" in runner.calls[1].stdin.decode("utf-8")
    assert "reread used doubtful_codes=0" in caplog.text


@pytest.mark.parametrize(
    "second",
    [
        ProcessOutput(0, stream({"type": "result", "subtype": "error", "finalText": ""}), b""),
        codes_output(),
        codes_output("SPXVN0000000001", "12345678901"),
    ],
    ids=["error", "lost-the-code", "more-doubtful"],
)
async def test_keeps_the_first_read_when_the_reread_is_not_better(cmdc_settings, second):
    runner = FakeRunner([codes_output("SPXVN00000000001"), second])
    result = await CmdcVisionEngine(cmdc_settings, runner).analyze_image(b"img")
    assert result.error is None
    assert result.tracking_codes == ("SPXVN00000000001",)
    assert len(runner.calls) == 2


async def test_a_failed_read_is_never_reread(cmdc_settings):
    runner = FakeRunner(ProcessOutput(1, b"", b"boom"))
    assert (
        await CmdcVisionEngine(cmdc_settings, runner).analyze_image(b"img")
    ).error == "cli_error"
    assert len(runner.calls) == 1


async def test_logs_hold_no_model_text_or_stderr(cmdc_settings, caplog):
    caplog.set_level("DEBUG")
    await CmdcVisionEngine(cmdc_settings, FakeRunner()).analyze_image(b"img")
    failing = ProcessOutput(
        1, stream({"type": "result", "finalText": RESULT_JSON}), b"stderr-secret"
    )
    await CmdcVisionEngine(cmdc_settings, FakeRunner(failing)).analyze_image(b"img")
    assert "SPXVN000000000001" not in caplog.text
    assert "Tai nghe" not in caplog.text
    assert "stderr-secret" not in caplog.text


async def test_the_run_does_not_inherit_bot_secrets(cmdc_settings, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:secret")
    monkeypatch.setenv("SEVENTEEN_TRACK_KEY", "17track-secret")
    monkeypatch.setenv("VN_PARCEL_MARKER", "keep-me")
    runner = FakeRunner()
    await CmdcVisionEngine(cmdc_settings, runner).analyze_image(b"img")

    env = runner.calls[0].env
    assert env is not None
    leaked = [
        key
        for key in env
        if key.upper().startswith(("ANTHROPIC_", "TELEGRAM_", "SEVENTEEN_TRACK_"))
    ]
    assert leaked == []
    assert env["VN_PARCEL_MARKER"] == "keep-me"


async def test_a_failed_image_write_is_an_error_not_an_exception(cmdc_settings, monkeypatch):
    def boom(self, data):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_bytes", boom)
    result = await CmdcVisionEngine(cmdc_settings, FakeRunner()).analyze_image(b"img")
    assert result.error == "cli_error"


async def test_run_process_passes_stdin_and_uses_the_given_environment(tmp_path):
    env = {**os.environ, "VN_PARCEL_MARKER": "from-env"}
    output = await run_process(
        [
            sys.executable,
            "-c",
            "import os, sys; sys.stdout.write(sys.stdin.read() + os.environ['VN_PARCEL_MARKER'])",
        ],
        b"prompt-",
        str(tmp_path),
        30,
        env,
    )
    assert output.returncode == 0
    assert output.stdout == b"prompt-from-env"


def test_agy_file_prompt_still_names_the_view_file_tool():
    assert file_prompt("a.png").startswith(
        "Use the view_file tool to open the image file a.png and use no other tool."
    )
    assert "count the characters" in file_prompt("a.png", reread=True)
    assert "count the characters" in tool_file_prompt("read_file", "a.png", reread=True)
