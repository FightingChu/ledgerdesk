"""The server executor completes queued reports and exposes bounded job pages."""
import time
from tests.support.http import HttpWorkspaceTest


class TaskHttpTests(HttpWorkspaceTest):
    def test_report_job_completes_and_download_is_owned_by_that_job(self):
        self.pair(count=1)
        status, job, _ = self.request("/api/jobs", {"kind": "report", "batch_id": self.batch, "payload": {"run_id": self.run}})
        self.assertEqual(status, 200)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            current = self.request("/api/jobs/" + job["id"])[1]
            if current["state"] in ("succeeded", "failed"):
                break
            time.sleep(0.05)
        self.assertEqual(current["state"], "succeeded")
        self.assertEqual(self.request("/api/jobs/" + job["id"] + "/download")[0], 200)
        manifest = self.request("/api/jobs/" + job["id"] + "/manifest")[1]
        self.assertEqual(manifest["metadata"]["run_id"], self.run)
        self.assertEqual(self.request("/api/jobs?page_size=101")[0], 400)

    def test_invalid_queue_is_all_or_nothing(self):
        status, _, _ = self.request("/api/jobs/queue", {"batch_ids": [self.batch, "missing"], "request_id": "HTTP queue"})
        self.assertEqual(status, 400)
        self.assertEqual(self.request("/api/jobs")[1]["total"], 0)
