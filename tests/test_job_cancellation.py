"""Cancellation is cooperative and does not revoke an already committed reconciliation."""
import threading
from ledgerdesk.application.jobs import JobService
from ledgerdesk.persistence.jobs import JobRepository
from ledgerdesk.runtime.job_context import JobContext
from ledgerdesk.domain.jobs.errors import JobCancelled, JobInterrupted
from tests.support.workspace import WorkspaceTest


class JobCancellationTests(WorkspaceTest):
    def test_queued_cancel_and_explicit_retry(self):
        service = JobService(self.store); job = service.enqueue("backup")
        self.assertEqual(service.cancel(job["id"])["state"], "cancelled")
        retried = service.retry(job["id"])
        self.assertEqual((retried["state"], retried["attempt"]), ("queued", 2))

    def test_running_cancel_is_observed_at_checkpoint(self):
        service = JobService(self.store); job = service.enqueue("backup")
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE"); running = JobRepository.claim(con)
        service.cancel(job["id"])
        with self.assertRaises(JobCancelled):
            JobContext(self.store, running, threading.Event()).checkpoint()

    def test_process_stop_is_distinguished_from_user_cancel(self):
        job = JobService(self.store).enqueue("backup"); stop = threading.Event(); stop.set()
        with self.assertRaises(JobInterrupted):
            JobContext(self.store, job, stop).checkpoint()
