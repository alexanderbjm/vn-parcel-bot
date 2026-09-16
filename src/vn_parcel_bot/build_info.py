import subprocess
import sys
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def deployed_revision() -> str | None:
    """Short commit and commit date of the checkout this process runs from, or None.

    Cached, so the one subprocess call happens on first use rather than per /health. Returns
    None when git is missing, the path is not a repository (an installed wheel, say) or the
    command fails, and the caller then leaves the line out.
    """
    args = [
        "git",
        "-C",
        str(REPO_ROOT),
        "log",
        "-1",
        "--format=%h|%cd",
        "--date=format:%d/%m/%Y",
    ]
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
    if result.returncode != 0:
        return None
    sha, separator, date = result.stdout.strip().partition("|")
    if not separator or not sha or not date:
        return None
    return f"{sha} · {date}"
