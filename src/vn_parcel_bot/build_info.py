import asyncio
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

MAX_COMMITS = 50

_cache: tuple[str, str] | None = None


def _git(*extra: str) -> list[str]:
    return ["git", "-C", str(REPO_ROOT), *extra]


def _run(args: list[str]) -> str | None:
    """Stdout of a git call, or None when git cannot answer."""
    try:
        result = subprocess.run(  # noqa: S603
            args,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def _lookup() -> tuple[str, str] | None:
    """Short commit and commit date of the checkout this process runs from, or None."""
    stdout = _run(_git("log", "-1", "--format=%h|%cd", "--date=format:%d/%m/%Y"))
    if stdout is None:
        return None
    sha, separator, date = stdout.strip().partition("|")
    if not separator or not sha or not date:
        return None
    return sha, date


def _revision() -> tuple[str, str] | None:
    global _cache
    if _cache is None:
        _cache = _lookup()
    return _cache


# Only a successful lookup is remembered: caching the failure too would hide the revision
# until the next restart on one transient hiccup, and /health is the diagnostic it serves.


def deployed_revision() -> str | None:
    """Short commit and commit date, ready to display, or None."""
    found = _revision()
    return f"{found[0]} · {found[1]}" if found else None


def deployed_revision_sha() -> str | None:
    """The short commit on its own, for comparing one start against the last."""
    found = _revision()
    return found[0] if found else None


def revision_commits(since: str | None) -> list[str]:
    """Subject lines of the commits after `since` up to HEAD, newest first.

    An empty list when there is nothing to compare against, when `since` is no longer a
    commit git can resolve (a rewritten branch), or when git cannot answer at all.
    """
    args = _git("log", f"-{MAX_COMMITS}", "--format=%s")
    if since:
        args.append(f"{since}..HEAD")
    stdout = _run(args)
    if stdout is None:
        return []
    return [line.strip() for line in stdout.splitlines() if line.strip()]


async def deployed_revision_async() -> str | None:
    """``deployed_revision()`` off the event loop.

    The lookup shells out to git, which would otherwise block every other handler, the poll cycle
    and the digests for the length of the call — up to its 10 s timeout.
    """
    return await asyncio.to_thread(deployed_revision)


async def deployed_revision_sha_async() -> str | None:
    return await asyncio.to_thread(deployed_revision_sha)


async def revision_commits_async(since: str | None) -> list[str]:
    return await asyncio.to_thread(revision_commits, since)
