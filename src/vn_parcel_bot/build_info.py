import asyncio
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_GIT_ARGS = [
    "git",
    "-C",
    str(REPO_ROOT),
    "log",
    "-1",
    "--format=%h|%cd",
    "--date=format:%d/%m/%Y",
]

_cache: str | None = None


def _lookup() -> str | None:
    try:
        result = subprocess.run(  # noqa: S603
            _GIT_ARGS,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    sha, separator, date = result.stdout.strip().partition("|")
    if not separator or not sha or not date:
        return None
    return f"{sha} · {date}"


def deployed_revision() -> str | None:
    """Short commit and commit date of the checkout this process runs from, or None.

    Returns None when git is missing, the path is not a repository (an installed wheel, say) or
    the command fails, and the caller then leaves the line out. Only a successful lookup is
    remembered: caching the failure too would hide the line until the next restart on one
    transient hiccup, and /health is the diagnostic that line exists for.
    """
    global _cache
    if _cache is None:
        _cache = _lookup()
    return _cache


async def deployed_revision_async() -> str | None:
    """``deployed_revision()`` off the event loop.

    The lookup shells out to git, which would otherwise block every other handler, the poll cycle
    and the digests for the length of the call — up to its 10 s timeout.
    """
    return await asyncio.to_thread(deployed_revision)
