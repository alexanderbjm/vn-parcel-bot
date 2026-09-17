from types import SimpleNamespace

import pytest

from vn_parcel_bot import build_info


@pytest.fixture(autouse=True)
def _clear_cache():
    build_info._cache = None
    yield
    build_info._cache = None


def completed(stdout: str, returncode: int = 0) -> SimpleNamespace:
    return SimpleNamespace(stdout=stdout, returncode=returncode)


def test_formats_short_sha_and_commit_date(monkeypatch):
    monkeypatch.setattr(
        build_info.subprocess, "run", lambda *a, **k: completed("1258faf|16/09/2026\n")
    )
    assert build_info.deployed_revision() == "1258faf · 16/09/2026"


def test_asks_git_for_the_head_commit_of_the_repo_root(monkeypatch):
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return completed("abc1234|01/01/2026\n")

    monkeypatch.setattr(build_info.subprocess, "run", fake_run)
    build_info.deployed_revision()

    assert seen["args"] == [
        "git",
        "-C",
        str(build_info.REPO_ROOT),
        "log",
        "-1",
        "--format=%h|%cd",
        "--date=format:%d/%m/%Y",
    ]
    assert seen["kwargs"]["check"] is False
    assert seen["kwargs"]["capture_output"] is True


@pytest.mark.parametrize(
    "stdout",
    ["", "\n", "1258faf\n", "|16/09/2026\n", "1258faf|\n", "no-separator\n"],
    ids=["empty", "blank", "sha-only", "date-only", "sha-and-empty-date", "no-separator"],
)
def test_missing_pieces_are_treated_as_unknown(monkeypatch, stdout):
    monkeypatch.setattr(build_info.subprocess, "run", lambda *a, **k: completed(stdout))
    assert build_info.deployed_revision() is None


def test_a_failing_git_is_treated_as_unknown(monkeypatch):
    monkeypatch.setattr(build_info.subprocess, "run", lambda *a, **k: completed("", 128))
    assert build_info.deployed_revision() is None


def test_a_missing_git_is_treated_as_unknown(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(build_info.subprocess, "run", boom)
    assert build_info.deployed_revision() is None


def test_a_hanging_git_is_treated_as_unknown(monkeypatch):
    def boom(*a, **k):
        raise build_info.subprocess.TimeoutExpired("git", 10)

    monkeypatch.setattr(build_info.subprocess, "run", boom)
    assert build_info.deployed_revision() is None


def test_the_lookup_runs_once_per_process(monkeypatch):
    calls = []

    def fake_run(*a, **k):
        calls.append(1)
        return completed("abc1234|01/01/2026\n")

    monkeypatch.setattr(build_info.subprocess, "run", fake_run)
    build_info.deployed_revision()
    build_info.deployed_revision()
    assert len(calls) == 1


def test_a_failed_lookup_is_not_remembered(monkeypatch):
    calls = []

    def fake_run(*a, **k):
        calls.append(1)
        return completed("", 128)

    monkeypatch.setattr(build_info.subprocess, "run", fake_run)
    assert build_info.deployed_revision() is None
    assert build_info.deployed_revision() is None
    # A transient failure must not hide the line until the next restart.
    assert len(calls) == 2


async def test_async_wrapper_returns_the_same_value(monkeypatch):
    monkeypatch.setattr(
        build_info.subprocess, "run", lambda *a, **k: completed("abc1234|01/01/2026\n")
    )
    assert await build_info.deployed_revision_async() == "abc1234 · 01/01/2026"


async def test_async_wrapper_runs_off_the_event_loop(monkeypatch):
    import threading

    seen = {}

    def fake_run(*a, **k):
        seen["thread"] = threading.current_thread().name
        return completed("abc1234|01/01/2026\n")

    monkeypatch.setattr(build_info.subprocess, "run", fake_run)
    await build_info.deployed_revision_async()
    assert seen["thread"] != threading.main_thread().name


def test_the_sha_and_the_display_string_share_one_lookup(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return completed("abc1234|01/01/2026\n")

    monkeypatch.setattr(build_info.subprocess, "run", fake_run)
    assert build_info.deployed_revision() == "abc1234 · 01/01/2026"
    assert build_info.deployed_revision_sha() == "abc1234"
    assert len(calls) == 1


def test_revision_commits_returns_subjects_and_bounds_the_range(monkeypatch):
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        return completed("feat: one\n\nfix: two\n")

    monkeypatch.setattr(build_info.subprocess, "run", fake_run)
    assert build_info.revision_commits("abc1234") == ["feat: one", "fix: two"]
    assert seen["args"][-1] == "abc1234..HEAD"


def test_revision_commits_without_a_base_lists_the_newest(monkeypatch):
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        return completed("feat: one\n")

    monkeypatch.setattr(build_info.subprocess, "run", fake_run)
    assert build_info.revision_commits(None) == ["feat: one"]
    assert not any("..HEAD" in arg for arg in seen["args"])


def test_revision_commits_is_empty_when_git_refuses(monkeypatch):
    # A rewritten branch leaves a recorded sha git can no longer resolve.
    monkeypatch.setattr(build_info.subprocess, "run", lambda *a, **k: completed("", 128))
    assert build_info.revision_commits("gone") == []


def test_revision_commits_is_empty_when_git_is_missing(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(build_info.subprocess, "run", boom)
    assert build_info.revision_commits(None) == []
