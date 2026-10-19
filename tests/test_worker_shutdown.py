"""Executor shutdown frees the OS lock and does not leave an idle thread behind."""
import time
import sqlite3
from unittest.mock import patch
from ledgerdesk.runtime.worker import JobWorker
from tests.support.workspace import WorkspaceTest


class WorkerShutdownTests(WorkspaceTest):
    def test_temporary_database_write_lock_does_not_kill_executor(self):
        worker = JobWorker(self.store)
        calls = []
        def attempt():
            calls.append(1)
            if len(calls) == 1:
                raise sqlite3.OperationalError("database is locked")
            worker.stop_event.set()
            return False
        with patch.object(worker, "run_once", side_effect=attempt):
            self.assertTrue(worker.start())
            worker.thread.join(timeout=5)
        worker.close()
        self.assertEqual(len(calls), 2)

    def test_idle_worker_closes_and_another_can_take_over(self):
        worker = JobWorker(self.store); self.assertTrue(worker.start())
        worker.close()
        self.assertFalse(worker.thread.is_alive())
        second = JobWorker(self.store); self.assertTrue(second.acquire()); second.close()
