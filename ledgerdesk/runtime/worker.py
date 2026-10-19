"""One local executor per workspace, durable queue claims and restart recovery."""
import logging
import threading
import sqlite3
from ..domain.jobs.errors import JobCancelled, JobInterrupted
from ..domain.errors import InputError
from ..domain.values import now
from ..persistence.jobs import JobRepository
from .workspace_lock import WorkspaceLock
from .job_context import JobContext
from .job_runners import execute

LOGGER = logging.getLogger("ledgerdesk.jobs")


class JobWorker:
    def __init__(self, store):
        self.store = store
        self.stop_event = threading.Event()
        self.lock = WorkspaceLock(store.path.parent / ".ledgerdesk-worker.lock")
        self.thread = None

    def acquire(self):
        if not self.lock.acquire():
            return False
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            from .recovery import recover_reports
            recover_reports(self.store, con)
            con.execute("UPDATE jobs SET state='interrupted',phase='上次进程中断，请重试',updated_at=? WHERE state='running'", (now(),))
        return True

    def run_once(self):
        if self.lock.handle is None:
            raise RuntimeError("Worker must hold the workspace lock")
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            job = JobRepository.claim(con)
        if job is None:
            return False
        context = JobContext(self.store, job, self.stop_event)
        state, result, error = "succeeded", None, ""
        try:
            result = execute(self.store, job, context)
        except JobCancelled:
            state = "cancelled"
        except JobInterrupted:
            state = "interrupted"
        except InputError as exc:
            state, error = "failed", str(exc)
        except Exception:
            LOGGER.exception("Local job failed")
            state, error = "failed", "任务执行失败，请查看本机日志"
        while True:
            try:
                with self.store.connect() as con:
                    con.execute("BEGIN IMMEDIATE")
                    JobRepository.transition(con, job["id"], state, result, error)
                break
            except sqlite3.OperationalError as exc:
                if not self._busy(exc):
                    raise
                if self.stop_event.wait(0.5):
                    break
        return True

    @staticmethod
    def _busy(error):
        return "locked" in str(error).lower() or "busy" in str(error).lower()

    def start(self):
        if not self.acquire():
            return False
        def loop():
            try:
                while not self.stop_event.is_set():
                    try:
                        if not self.run_once():
                            self.stop_event.wait(0.25)
                    except sqlite3.OperationalError as exc:
                        if not self._busy(exc):
                            raise
                        self.stop_event.wait(0.5)
            finally:
                self.lock.release()
        self.thread = threading.Thread(target=loop, name="ledgerdesk-jobs", daemon=True)
        self.thread.start()
        return True

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        else:
            self.lock.release()
