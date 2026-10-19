"""Execution succeeds only for the queued input identity."""
from ledgerdesk.application.jobs import JobService
from ledgerdesk.runtime.worker import JobWorker
from ledgerdesk.domain.errors import InputError
from tests.support.workspace import WorkspaceTest


class JobLifecycleTests(WorkspaceTest):
    def worker(self):
        worker = JobWorker(self.store)
        self.assertTrue(worker.acquire()); self.addCleanup(worker.close)
        return worker

    def test_reconciliation_job_and_completed_retry_rejection(self):
        self.pair(count=1)
        service = JobService(self.store)
        job = service.enqueue("reconcile", self.batch)
        self.worker().run_once()
        result = service.get(job["id"])
        self.assertEqual((result["state"], result["progress"]), ("succeeded", 1))
        self.assertEqual(result["result"]["run_id"], self.run)
        with self.assertRaises(InputError):
            service.retry(job["id"])

    def test_changed_inputs_fail_instead_of_reconciling_new_data(self):
        self.pair(count=1)
        service = JobService(self.store); job = service.enqueue("reconcile", self.batch)
        self.add("orders", "order_id,amount,channel\nNEW,1,x\n")
        self.worker().run_once()
        self.assertEqual(service.get(job["id"])["state"], "failed")
        self.assertEqual(self.store.overview(self.batch)["run"]["id"], self.run)
        with self.assertRaises(InputError):
            service.retry(job["id"])
