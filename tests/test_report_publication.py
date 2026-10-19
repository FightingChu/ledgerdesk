"""Generated task reports are exclusive, hashed and recoverable."""
import hashlib
import json
from ledgerdesk.application.jobs import JobService
from ledgerdesk.runtime.worker import JobWorker
from tests.support.workspace import WorkspaceTest


class ReportPublicationTests(WorkspaceTest):
    def test_successful_report_has_matching_hash_and_no_partial_file(self):
        self.pair(count=2)
        service = JobService(self.store); job = service.enqueue("report", self.batch, {"run_id": self.run})
        worker = JobWorker(self.store); self.assertTrue(worker.acquire()); self.addCleanup(worker.close)
        worker.run_once(); result = service.get(job["id"])
        self.assertEqual(result["state"], "succeeded")
        self.assertEqual(result["result"]["metadata"]["run_id"], self.run)
        path = self.root / "exports" / result["result"]["filename"]
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), result["result"]["sha256"])
        self.assertEqual(list(path.parent.glob("*.partial")), [])

    def test_completed_file_is_recovered_after_publication_before_job_commit(self):
        self.pair(count=1)
        service = JobService(self.store); job = service.enqueue("report", self.batch, {"run_id": self.run})
        directory = self.root / "exports"; directory.mkdir()
        data = b"synthetic published report"; name = job["id"] + ".csv"
        (directory / name).write_bytes(data)
        with self.store.connect() as con:
            con.execute("UPDATE jobs SET state='running',result=? WHERE id=?", (json.dumps({"filename": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}), job["id"]))
        worker = JobWorker(self.store); self.assertTrue(worker.acquire()); self.addCleanup(worker.close)
        self.assertEqual(service.get(job["id"])["state"], "succeeded")
