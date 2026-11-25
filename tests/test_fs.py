import os
import subprocess
import sys
import textwrap

import pytest

from tgcs.fs import MsvcrtLocker

WINDOWS_PRELUDE = """
import asyncio
import subprocess
import sys
import types

held = set()


def locking(fd, mode, size):
    import os

    stat = os.fstat(fd)
    key = (stat.st_dev, stat.st_ino)
    if mode == fake.LK_UNLCK:
        held.discard(key)
    elif key in held:
        raise PermissionError("locked")
    else:
        held.add(key)


fake = types.ModuleType("msvcrt")
fake.LK_NBLCK = 2
fake.LK_UNLCK = 0
fake.locking = locking
sys.modules["fcntl"] = None
sys.modules["msvcrt"] = fake
"""


def _run_without_fcntl(code, *args):
    script = textwrap.dedent(WINDOWS_PRELUDE) + textwrap.dedent(code)
    return subprocess.run(
        [sys.executable, "-c", script, *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


class FakeMsvcrt:
    LK_NBLCK = 2
    LK_UNLCK = 0

    def __init__(self, failures=0):
        self.failures = failures
        self.calls = []

    def locking(self, fd, mode, size):
        self.calls.append((mode, os.lseek(fd, 0, os.SEEK_CUR), size))
        if self.failures:
            self.failures -= 1
            raise PermissionError("locked")


@pytest.fixture
def fd(tmp_path):
    fd = os.open(tmp_path / "file.lock", os.O_CREAT | os.O_RDWR)
    yield fd
    os.close(fd)


def test_cli_starts_without_fcntl():
    # when
    result = _run_without_fcntl(
        """
        from typer.testing import CliRunner

        from tgcs.cli import create_app

        result = CliRunner().invoke(create_app(lambda _: None), ["--help"])
        assert result.exit_code == 0, result.output
        """
    )

    # then
    assert result.returncode == 0, result.stderr


def test_metadata_and_summary_locks_work_without_fcntl(tmp_path):
    # when
    result = _run_without_fcntl(
        """
        from tgcs.layouts import Layout
        from tgcs.paths import FilePathManager
        from tgcs.summary_creator import SummaryCreator

        pm = FilePathManager(base_path=sys.argv[1])
        pm.create_folders_if_not_exists("team", "2025-01-01")
        pm.write_metadata("team", {"id": 1})
        for layout in (Layout.SINGLE, Layout.DAILY):
            assert pm.set_layout("team", layout)
            assert pm.layout("team") is layout
        assert [name for name, _, _ in pm.all_groups_list()] == ["team"]
        first = SummaryCreator(pm, workflow=None)
        second = SummaryCreator(pm, workflow=None)
        assert first._acquire_lock("team", "2025-01-01")
        assert not second._acquire_lock("team", "2025-01-01")
        first._release_lock("team", "2025-01-01")
        assert second._acquire_lock("team", "2025-01-01")
        """,
        str(tmp_path / "data"),
    )

    # then
    assert result.returncode == 0, result.stderr


def test_msvcrt_try_lock_reports_a_held_lock(fd):
    # given
    locker = MsvcrtLocker(FakeMsvcrt(failures=1))

    # when / then
    assert locker.try_lock(fd) is False
    assert locker.try_lock(fd) is True


def test_msvcrt_lock_waits_until_the_lock_is_free(fd):
    # given
    msvcrt = FakeMsvcrt(failures=2)
    sleeps = []
    locker = MsvcrtLocker(msvcrt, sleep=sleeps.append)

    # when
    locker.lock(fd)

    # then
    assert len(msvcrt.calls) == 3
    assert len(sleeps) == 2


def test_msvcrt_lock_leaves_the_file_position_at_the_start(fd):
    # given
    msvcrt = FakeMsvcrt()
    locker = MsvcrtLocker(msvcrt)

    # when
    locker.lock(fd)
    os.write(fd, b"42")
    locker.unlock(fd)

    # then
    os.lseek(fd, 0, os.SEEK_SET)
    assert os.read(fd, 10) == b"42"
    assert msvcrt.calls[0][1] == msvcrt.calls[1][1] > 2
