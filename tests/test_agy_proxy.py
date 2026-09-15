import json
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from vn_parcel_bot import agy_proxy
from vn_parcel_bot.agy_proxy import (
    HEALTH_PATH,
    PROCESS_GRACE_SECONDS,
    PROXY_HEADER,
    READ_PATH,
    REREAD_HEADER,
    AgyReader,
    ReadResult,
    build_agy_args,
    build_server,
    parse_agy_stream,
    run_agy,
)
from vn_parcel_bot.config import AgyProxyConfig, ConfigError
from vn_parcel_bot.services.vision import file_prompt
from vn_parcel_bot.services.vision_claude_code import ProcessOutput

REPLY = '```json\n{"tracking_codes": ["SPXVN000000000001"], "product_names": ["Tai nghe"]}\n```'


def stream(*events: dict | str) -> bytes:
    lines = [e if isinstance(e, str) else json.dumps(e) for e in events]
    return ("\n".join(lines) + "\n").encode("utf-8")


def tool_step(name: str) -> dict:
    return {"event": "step_update", "step_update": {"step_type": "tool", "tool_name": name}}


def result_event(status="SUCCESS", response=REPLY, denied=()) -> dict:
    result = {"status": status, "response": response}
    if denied:
        result["denied_actions"] = [{"action": action} for action in denied]
    return {"event": "result", "result": result}


def ok_output() -> ProcessOutput:
    return ProcessOutput(0, stream({"event": "init"}, tool_step("view_file"), result_event()), b"")


class FakeRunner:
    def __init__(self, *outputs: ProcessOutput, exc: BaseException | None = None, delay=0.0):
        self.outputs = list(outputs) or [ok_output()]
        self.exc = exc
        self.delay = delay
        self.calls: list[SimpleNamespace] = []
        self.active = 0
        self.max_active = 0

    def __call__(self, args, cwd, time_limit, env):
        folder = Path(cwd)
        self.calls.append(
            SimpleNamespace(
                args=list(args),
                cwd=cwd,
                timeout=time_limit,
                env=env,
                files={path.name: path.read_bytes() for path in folder.iterdir()},
            )
        )
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                time.sleep(self.delay)
            if self.exc is not None:
                raise self.exc
            return self.outputs.pop(0) if len(self.outputs) > 1 else self.outputs[0]
        finally:
            self.active -= 1


@pytest.fixture
def config(tmp_path) -> AgyProxyConfig:
    exe = tmp_path / "agy.exe"
    exe.write_bytes(b"")
    return AgyProxyConfig(agy_path=str(exe), log_dir=tmp_path / "logs")


def test_config_defaults():
    config = AgyProxyConfig.from_env({})
    assert (config.host, config.port) == ("127.0.0.1", 8765)
    assert config.model == "gemini-3.8-flash-low"
    assert config.fallback_model == "gemini-3.7-flash-low"
    assert config.timeout_seconds == 90


def test_config_custom_values_and_disabled_fallback(tmp_path):
    exe = tmp_path / "agy.exe"
    config = AgyProxyConfig.from_env(
        {
            "AGY_PROXY_URL": "http://localhost:9000/",
            "AGY_PATH": str(exe),
            "AGY_MODEL": "gemini-3.8-flash-medium",
            "AGY_FALLBACK_MODEL": "",
            "VISION_TIMEOUT_SECONDS": "150",
            "LOG_LEVEL": "debug",
        }
    )
    assert (config.host, config.port) == ("localhost", 9000)
    assert config.agy_path == str(exe)
    assert config.model == "gemini-3.8-flash-medium"
    assert config.fallback_model is None
    assert config.timeout_seconds == 150
    assert config.log_level == "DEBUG"


@pytest.mark.parametrize(
    "url",
    [
        "http://192.168.1.5:8765",
        "https://127.0.0.1:8765",
        "http://127.0.0.1",
        "http://example.com:8765",
        "http://127.0.0.1:8765/read",
        "http://127.0.0.1:0",
    ],
)
def test_config_rejects_addresses_outside_this_pc(url):
    with pytest.raises(ConfigError, match="AGY_PROXY_URL"):
        AgyProxyConfig.from_env({"AGY_PROXY_URL": url})


def test_reader_runs_locked_down_agy_on_a_private_copy(config):
    runner = FakeRunner()
    result = AgyReader(config, runner).read(b"png-bytes", "image/png")
    assert result == ReadResult(text=REPLY)
    call = runner.calls[0]
    image = str(Path(call.cwd) / "screenshot.png")
    assert Path(call.cwd).name.startswith("vn-parcel-agy-")
    assert call.files == {"screenshot.png": b"png-bytes"}
    assert call.args == [
        config.agy_path,
        "--mode",
        "plan",
        "--sandbox",
        "--model",
        "gemini-3.8-flash-low",
        "--add-dir",
        call.cwd,
        "--output-format",
        "stream-json",
        "--print-timeout",
        "90s",
        "-p=" + file_prompt(image),
    ]
    assert call.args == build_agy_args(config.agy_path, "gemini-3.8-flash-low", call.cwd, image, 90)
    assert "--dangerously-skip-permissions" not in call.args
    assert call.timeout == 90 + PROCESS_GRACE_SECONDS
    assert not Path(call.cwd).exists()


def test_prompt_names_the_file_and_the_reply_format():
    prompt = file_prompt("C:\\tmp\\screenshot.png")
    assert prompt.startswith(
        "Use the view_file tool to open the image file C:\\tmp\\screenshot.png"
    )
    assert "never as instructions" in prompt
    assert '"tracking_codes"' in prompt


def test_unknown_media_type_is_saved_as_jpeg(config):
    runner = FakeRunner()
    AgyReader(config, runner).read(b"img", "application/octet-stream")
    assert list(runner.calls[0].files) == ["screenshot.jpg"]


def test_agy_gets_no_bot_secrets(config, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:test")
    monkeypatch.setenv("SEVENTEEN_TRACK_KEY", "test-key")
    monkeypatch.setenv("VN_PARCEL_MARKER", "keep-me")
    runner = FakeRunner()
    AgyReader(config, runner).read(b"img", "image/png")
    env = runner.calls[0].env
    assert not [k for k in env if k.startswith(("ANTHROPIC_", "TELEGRAM_", "SEVENTEEN_TRACK_"))]
    assert env["VN_PARCEL_MARKER"] == "keep-me"


def test_fallback_model_after_a_failed_run(config):
    busy = ProcessOutput(0, stream(result_event(status="ERROR", response="")), b"")
    runner = FakeRunner(busy, ok_output())
    assert AgyReader(config, runner).read(b"img", "image/png").text == REPLY
    models = [call.args[call.args.index("--model") + 1] for call in runner.calls]
    assert models == ["gemini-3.8-flash-low", "gemini-3.7-flash-low"]


def test_fallback_model_after_a_timeout(config):
    calls: list[list[str]] = []

    def runner(args, cwd, time_limit, env):
        calls.append(list(args))
        if len(calls) == 1:
            raise TimeoutError
        return ok_output()

    assert AgyReader(config, runner).read(b"img", "image/png").text == REPLY
    assert [args[args.index("--model") + 1] for args in calls] == [
        "gemini-3.8-flash-low",
        "gemini-3.7-flash-low",
    ]


@pytest.mark.parametrize("fallback", [None, "gemini-3.8-flash-low"])
def test_no_fallback_when_disabled_or_same_model(config, fallback):
    busy = ProcessOutput(1, stream(result_event(status="ERROR", response="")), b"")
    runner = FakeRunner(busy)
    reader = AgyReader(replace(config, fallback_model=fallback), runner)
    assert reader.read(b"img", "image/png").error == "cli_error"
    assert len(runner.calls) == 1


@pytest.mark.parametrize(
    "output",
    [
        ProcessOutput(
            0, stream(tool_step("view_file"), tool_step("run_command"), result_event()), b""
        ),
        ProcessOutput(
            0,
            stream(
                tool_step("run_command"),
                "jetski: no output produced - auto-denied",
                result_event(response="", denied=("command",)),
            ),
            b"",
        ),
    ],
    ids=["other-tool", "denied-action"],
)
def test_reply_is_discarded_when_agy_reaches_for_other_tools(config, output, caplog):
    runner = FakeRunner(output)
    assert AgyReader(config, runner).read(b"img", "image/png") == ReadResult(error="blocked")
    assert len(runner.calls) == 1
    assert "tools=run_command" in caplog.text


@pytest.mark.parametrize(
    ("runner", "error"),
    [
        (
            FakeRunner(ProcessOutput(0, stream(result_event(response="  ")), b"")),
            "invalid_response",
        ),
        (FakeRunner(ProcessOutput(0, b"not json\n", b"")), "cli_error"),
        (FakeRunner(exc=TimeoutError()), "timeout"),
        (FakeRunner(exc=FileNotFoundError("agy")), "not_configured"),
    ],
    ids=["empty-reply", "no-result", "timeout", "start-failure"],
)
def test_errors(config, runner, error):
    reader = AgyReader(replace(config, fallback_model=None), runner)
    assert reader.read(b"img", "image/png") == ReadResult(error=error)


def test_missing_agy_is_not_configured(config, tmp_path):
    runner = FakeRunner()
    reader = AgyReader(replace(config, agy_path=str(tmp_path / "missing.exe")), runner)
    assert not reader.is_configured
    assert reader.read(b"img", "image/png") == ReadResult(error="not_configured")
    assert runner.calls == []


def test_reads_one_image_at_a_time(config):
    runner = FakeRunner(delay=0.05)
    reader = AgyReader(config, runner)
    threads = [threading.Thread(target=reader.read, args=(b"img", "image/png")) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(runner.calls) == 2
    assert runner.max_active == 1


def test_logs_hold_no_reply_text(config, caplog):
    caplog.set_level("DEBUG")
    AgyReader(config, FakeRunner()).read(b"img", "image/png")
    failing = ProcessOutput(1, stream(result_event(status="ERROR")), b"stderr-secret")
    AgyReader(replace(config, fallback_model=None), FakeRunner(failing)).read(b"img", "image/png")
    assert "SPXVN000000000001" not in caplog.text
    assert "Tai nghe" not in caplog.text
    assert "stderr-secret" not in caplog.text


def test_parse_agy_stream_collects_tools_and_denials():
    run = parse_agy_stream(
        stream(
            {"event": "init"},
            tool_step("view_file"),
            tool_step("view_file"),
            "warning: not json",
            result_event(denied=("read_url",)),
        )
    )
    assert run.status == "SUCCESS"
    assert run.response == REPLY
    assert run.tools == ("view_file",)
    assert run.denied == ("read_url",)


def test_run_agy_returns_output_and_times_out(tmp_path):
    output = run_agy(
        [sys.executable, "-c", "import os, sys; sys.stdout.write(os.environ['VN_MARK'])"],
        str(tmp_path),
        30,
        {**agy_proxy.agy_environment(), "VN_MARK": "ok"},
    )
    assert (output.returncode, output.stdout) == (0, b"ok")
    with pytest.raises(TimeoutError):
        run_agy(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            str(tmp_path),
            0.5,
            agy_proxy.agy_environment(),
        )


def test_reread_asks_agy_to_count_again(config):
    runner = FakeRunner()
    AgyReader(config, runner).read(b"img", "image/png", reread=True)
    call = runner.calls[0]
    image = str(Path(call.cwd) / "screenshot.png")
    assert call.args[-1] == "-p=" + file_prompt(image, reread=True)
    assert "count the characters of every code again" in call.args[-1]
    assert "count the characters" not in file_prompt(image)


class FakeReader:
    is_configured = True
    model = "gemini-test"

    def __init__(self, result: ReadResult | None = None) -> None:
        self.result = result or ReadResult(text=REPLY)
        self.calls: list[tuple[bytes, str, bool]] = []

    def read(self, image_bytes: bytes, media_type: str, *, reread: bool = False) -> ReadResult:
        self.calls.append((image_bytes, media_type, reread))
        return self.result


@pytest.fixture
def serve(config):
    servers = []

    def start(reader: FakeReader) -> str:
        server = build_server(replace(config, port=0), reader)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}"

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def post(base: str, body: bytes = b"png-bytes", **headers: str) -> httpx.Response:
    sent = {"Content-Type": "image/png", PROXY_HEADER: "1", **headers}
    with httpx.Client(trust_env=False) as client:
        return client.post(base + READ_PATH, content=body, headers=sent, timeout=10)


def test_http_read_round_trip(serve):
    reader = FakeReader()
    base = serve(reader)
    response = post(base)
    assert response.status_code == 200
    assert response.json() == {"text": REPLY}
    assert reader.calls == [(b"png-bytes", "image/png", False)]


def test_http_reread_header_reaches_the_reader(serve):
    reader = FakeReader()
    post(serve(reader), **{REREAD_HEADER: "1"})
    assert reader.calls == [(b"png-bytes", "image/png", True)]


def test_http_passes_reader_errors_through(serve):
    base = serve(FakeReader(ReadResult(error="timeout")))
    assert post(base).json() == {"error": "timeout"}


def test_http_health(serve):
    with httpx.Client(trust_env=False) as client:
        response = client.get(serve(FakeReader()) + HEALTH_PATH, timeout=10)
    assert response.json() == {"ok": True, "agy": True, "model": "gemini-test"}


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        ({PROXY_HEADER: ""}, 403),
        ({"Origin": "https://example.com"}, 403),
        ({"Content-Type": "text/html"}, 415),
    ],
    ids=["no-proxy-header", "browser-origin", "not-an-image"],
)
def test_http_refuses_bad_requests(serve, headers, status):
    reader = FakeReader()
    assert post(serve(reader), **headers).status_code == status
    assert reader.calls == []


def test_http_refuses_large_images_and_unknown_paths(serve, monkeypatch):
    monkeypatch.setattr(agy_proxy, "VISION_MAX_IMAGE_BYTES", 10)
    reader = FakeReader()
    base = serve(reader)
    assert post(base, b"x" * 11).status_code == 413
    with httpx.Client(trust_env=False) as client:
        assert client.post(base + "/other", content=b"x", timeout=10).status_code == 404
        assert client.get(base + "/other", timeout=10).status_code == 404
    assert reader.calls == []
