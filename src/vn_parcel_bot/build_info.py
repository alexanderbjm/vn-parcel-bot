import asyncio
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

MAX_COMMITS = 50

# The bot's update notice is read by a person, so it must not print a commit subject: those are
# written for the repository and for git — "Refuse a cached hub that sits off the route, and read
# a bare hub code" says nothing to the admin in Telegram. A commit therefore says what changed in
# Vietnamese on a line of its own in the body, and that line is what the notice shows.
VI_NOTE = "vi:"

_cache: tuple[str, str] | None = None


def _git(*extra: str) -> list[str]:
    return ["git", "-C", str(REPO_ROOT), *extra]


def _run(args: list[str]) -> str | None:
    """Stdout of a git call, or None when git cannot answer."""
    try:
        result = subprocess.run(  # noqa: S603
            args,
            capture_output=True,
            # git writes UTF-8, while the console codepage here is cp1252: decoded as the
            # console says, a "Vi:" note with Vietnamese diacritics raises inside the reader
            # thread and the call yields nothing, which silently empties the update notice.
            encoding="utf-8",
            errors="replace",
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


def _note(subject: str, body: Sequence[str]) -> str:
    """The one line the notice shows for a commit: its Vietnamese note, or its subject.

    A commit with no note still says something rather than dropping out of the notice, so a
    change is never invisible just because its wording was forgotten.
    """
    for line in body:
        stripped = line.strip()
        if stripped.casefold().startswith(VI_NOTE):
            note = stripped[len(VI_NOTE) :].strip()
            if note:
                return note
    return subject


def revision_commits(since: str | None) -> list[str]:
    """What each commit after `since` changed, newest first, in the wording the notice shows.

    An empty list when there is nothing to compare against, when `since` is no longer a
    commit git can resolve (a rewritten branch), or when git cannot answer at all.
    """
    args = _git("log", f"-{MAX_COMMITS}", "--format=%s%n%b%x00")
    if since:
        args.append(f"{since}..HEAD")
    stdout = _run(args)
    if stdout is None:
        return []
    notes = []
    for record in stdout.split("\x00"):
        lines = [line.strip() for line in record.strip().splitlines()]
        if not lines or not lines[0]:
            continue
        notes.append(_note(lines[0], lines[1:]))
    return notes


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
