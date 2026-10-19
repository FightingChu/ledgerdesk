"""An OS lock prevents two executors from recovering each other's running jobs."""
from ledgerdesk.runtime.workspace_lock import WorkspaceLock
from tests.support.workspace import WorkspaceTest


class WorkspaceLockTests(WorkspaceTest):
    def test_second_owner_waits_until_first_releases(self):
        a = WorkspaceLock(self.root / "worker.lock"); b = WorkspaceLock(self.root / "worker.lock")
        self.addCleanup(a.release); self.addCleanup(b.release)
        self.assertTrue(a.acquire()); self.assertFalse(b.acquire())
        a.release(); self.assertTrue(b.acquire())

    def test_release_keeps_lock_inode_available_for_later_owners(self):
        path = self.root / "worker.lock"; lock = WorkspaceLock(path)
        self.assertTrue(lock.acquire()); lock.release()
        self.assertTrue(path.exists())
        again = WorkspaceLock(path); self.assertTrue(again.acquire()); again.release()
