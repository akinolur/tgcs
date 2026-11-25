import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

try:
    import fcntl
except ImportError:
    fcntl = None
    import msvcrt

_LOCK_POSITION = 1 << 30
_RETRY_SECONDS = 0.05


class FlockLocker:
    def lock(self, fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX)

    def try_lock(self, fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True

    def unlock(self, fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


class MsvcrtLocker:
    def __init__(self, msvcrt, sleep: Callable[[float], None] = time.sleep):
        self._msvcrt = msvcrt
        self._sleep = sleep

    def lock(self, fd: int) -> None:
        while not self.try_lock(fd):
            self._sleep(_RETRY_SECONDS)

    def try_lock(self, fd: int) -> bool:
        try:
            self._locking(fd, self._msvcrt.LK_NBLCK)
        except PermissionError:
            return False
        return True

    def unlock(self, fd: int) -> None:
        self._locking(fd, self._msvcrt.LK_UNLCK)

    def _locking(self, fd: int, mode: int) -> None:
        os.lseek(fd, _LOCK_POSITION, os.SEEK_SET)
        try:
            self._msvcrt.locking(fd, mode, 1)
        finally:
            os.lseek(fd, 0, os.SEEK_SET)


locker = FlockLocker() if fcntl else MsvcrtLocker(msvcrt)


@contextmanager
def lock_file(path: str) -> Iterator[None]:
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        locker.lock(fd)
        try:
            yield
        finally:
            locker.unlock(fd)
    finally:
        os.close(fd)


def fsync_folder(path: str) -> None:
    if not fcntl:
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
