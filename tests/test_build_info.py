from types import SimpleNamespace

import pytest

from vn_parcel_bot import build_info


@pytest.fixture(autouse=True)
def _clear_cache():
    build_info.deployed_revision.cache_clear()
    yield
    build_info.deployed_revision.cache_clear()


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
