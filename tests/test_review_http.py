"""Version-required HTTP writes and audit pagination through real localhost requests."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from ledgerdesk.server import make_server


class ReviewHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = make_server(Path(self.temp.name) / "http.sqlite3", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.token = self.request("/api/bootstrap")[1]["token"]
        self.batch = self.request("/api/demo", {})[1]["batch_id"]
        self.prefix = f"/api/batches/{self.batch}/"
        data = self.request(self.prefix + "results?group=issues")[1]
        self.run = data["run_id"]
        self.items = [{"case_key": r["case_key"], "evidence_sha256": r["evidence_sha256"],
                       "expected_revision": r["review_revision"]} for r in data["items"][:2]]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, payload=None, extra=None):
        headers = {} if payload is None else {"Content-Type": "application/json", "X-LedgerDesk-Token": self.token}
        headers.update(extra or {})
        body = None if payload is None else json.dumps(payload).encode()
        try:
            response = urlopen(Request(self.url + path, body, headers), timeout=20)
        except HTTPError as error:
            response = error
        with response:
            content = response.read()
            return response.status, json.loads(content) if response.headers.get("Content-Type", "").startswith("application/json") else content

    def test_bulk_save_retry_conflict_and_audit_links_are_consistent(self):
        payload = {"run_id": self.run, "items": self.items, "status": "resolved", "note": "synthetic HTTP checked"}
        status, saved = self.request(self.prefix + "bulk-review", payload)
        self.assertEqual((status, saved["count"]), (200, 2))
        status, conflict = self.request(self.prefix + "bulk-review", payload)
        self.assertEqual((status, conflict["code"]), (400, "review_conflict"))
        status, audit = self.request(self.prefix + "audit?action=bulk_review&page_size=1")
        self.assertEqual((status, audit["total"]), (200, 1))
        self.assertEqual(audit["items"][0]["payload"]["operation_id"], saved["operation_id"])
        status, individual = self.request(self.prefix + "audit?action=review")
        self.assertEqual((status, individual["total"]), (200, 2))

    def test_single_save_requires_versions_and_detects_other_page(self):
        item = self.items[0]
        payload = {**item, "run_id": self.run, "status": "in_progress", "note": "one page"}
        for field in ("run_id", "expected_revision"):
            missing = {k: v for k, v in payload.items() if k != field}
            self.assertEqual(self.request(self.prefix + "review", missing)[0], 400)
        self.assertEqual(self.request(self.prefix + "review", payload)[0], 200)
        status, conflict = self.request(self.prefix + "review", payload)
        self.assertEqual((status, conflict["code"]), (400, "review_conflict"))
        case = self.request(self.prefix + "cases/" + item["case_key"] + "?run_id=" + self.run)[1]["item"]
        self.assertEqual(case["review_revision"], 1)

    def test_invalid_bulk_scope_token_origin_and_audit_parameters_are_rejected(self):
        payload = {"run_id": self.run, "items": self.items, "status": "resolved", "note": "synthetic"}
        for extra in ({"X-LedgerDesk-Token": "wrong"}, {"Origin": "https://invalid.example"}):
            self.assertEqual(self.request(self.prefix + "bulk-review", payload, extra)[0], 403)
        other = self.request("/api/batches", {"name": "another"})[1]["batch_id"]
        self.assertEqual(self.request(f"/api/batches/{other}/bulk-review", payload)[0], 400)
        for query in ("action=nope", "action=review&action=bulk_review", "until_id=", "until_id=-1", "until_id=1&until_id=2",
                      "until_id=9999999999999999999", "page_size=101", "page=1&page=2"):
            with self.subTest(query=query):
                self.assertEqual(self.request(self.prefix + "audit?" + query)[0], 400)
