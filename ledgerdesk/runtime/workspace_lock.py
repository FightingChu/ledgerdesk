"""Hold an OS file lock for the worker lifetime; never delete the lock inode."""
import os
from pathlib import Path


class WorkspaceLock:
    def __init__(self, path):
        self.path = Path(path)
        self.handle = None

    def acquire(self):
        if self.path.is_symlink():
            raise OSError("任务锁不能是链接")
        handle = self.path.open("a+b")
        try:
            if handle.tell() == 0:
                handle.write(b"0"); handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self.handle = handle
        return True

    def release(self):
        if self.handle is not None:
            self.handle.close()
            self.handle = None
