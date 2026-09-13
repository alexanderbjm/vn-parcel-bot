import pytest

from vn_parcel_bot.single_instance import SingleInstanceError, SingleInstanceLock


def test_second_lock_fails_then_succeeds_after_release(tmp_path):
    path = tmp_path / "bot.lock"
    with SingleInstanceLock(path), pytest.raises(SingleInstanceError), SingleInstanceLock(path):
        pass
    with SingleInstanceLock(path):
        pass


def test_creates_parent_directory(tmp_path):
    path = tmp_path / "nested" / "dir" / "bot.lock"
    with SingleInstanceLock(path):
        assert path.parent.is_dir()
