"""Recovery occurs only while holding the workspace execution lock."""
from ledgerdesk.application.jobs import JobService
from ledgerdesk.persistence.jobs import JobRepository
from ledgerdesk.runtime.worker import JobWorker
from tests.support.workspace import WorkspaceTest


class JobRecoveryTests(WorkspaceTest):
    def test_running_job_becomes_interrupted_after_restart(self):
        service = JobService(self.store); job = service.enqueue("backup")
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE"); JobRepository.claim(con)
        worker = JobWorker(self.store)
        self.assertTrue(worker.acquire()); self.addCleanup(worker.close)
        self.assertEqual(service.get(job["id"])["state"], "interrupted")
        self.assertEqual(service.retry(job["id"])["attempt"], 2)

    def test_worker_without_lock_cannot_claim(self):
        worker = JobWorker(self.store)
        with self.assertRaises(RuntimeError):
            worker.run_once()
