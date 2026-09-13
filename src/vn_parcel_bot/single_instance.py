import sys
from pathlib import Path
from typing import IO, Self


class SingleInstanceError(RuntimeError):
    pass


class SingleInstanceLock:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._handle: IO[bytes] | None = None

    def __enter__(self) -> Self:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self._path, "a+b")
        try:
            handle.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise SingleInstanceError(f"lock held: {self._path}") from exc
        self._handle = handle
        return self

    def __exit__(self, *exc_info: object) -> None:
        handle = self._handle
        if handle is None:
            return
        try:
            handle.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            handle.close()
            self._handle = None
