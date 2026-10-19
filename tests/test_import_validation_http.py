"""Preflight and confirmation contracts through a real localhost HTTP server."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from ledgerdesk.server import make_server
from tests.test_ingestion import encoded


class ImportValidationHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = make_server(Path(self.temp.name) / "http.sqlite3", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.token = self.request("/api/bootstrap")[1]["token"]
        self.batch = self.request("/api/batches", {"name": "synthetic wizard"})[1]["batch_id"]
        self.prefix = f"/api/batches/{self.batch}/"
        self.payload = {"side": "orders", "filename": "synthetic.csv", "content": encoded("order_id,amount,channel\n0001,1,x\n"),
                        "mapping": {"order_id": "order_id", "amount": "amount", "channel": "channel"}}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, payload=None, headers=None):
        extra = {} if payload is None else {"Content-Type": "application/json", "X-LedgerDesk-Token": self.token}
        extra.update(headers or {})
        try:
            response = urlopen(Request(self.url + path, None if payload is None else json.dumps(payload).encode(), extra), timeout=20)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            return response.status, json.loads(raw) if response.headers.get("Content-Type", "").startswith("application/json") else raw

    def test_preview_suggestions_require_confirmation_and_unknown_versions_are_rejected(self):
        self.request("/api/templates", {"name": "synthetic template", "side": "orders", "mapping": self.payload["mapping"]})
        status, preview = self.request("/api/preview", self.payload)
        self.assertEqual(status, 200)
        self.assertEqual(len(preview["template_suggestions"]), 1)
        self.assertEqual(preview["adapter"]["version"], 1)
        self.assertEqual(preview["encoding"], "utf-8")
        status, error = self.request("/api/preview", dict(self.payload, adapter_version=99))
        self.assertEqual((status, error["code"]), (400, "unsupported_adapter"))

    def test_preflight_no_write_confirmation_and_replay_rejection(self):
        status, checked = self.request(self.prefix + "validate-import", self.payload)
        self.assertEqual((status, checked["valid"]), (200, True))
        self.assertEqual(self.request(self.prefix + "overview")[1]["imports"], [])
        payload = dict(self.payload, receipt=checked["receipt"])
        self.assertEqual(self.request(self.prefix + "import", payload)[0], 200)
        status, error = self.request(self.prefix + "import", payload)
        self.assertEqual((status, error["code"]), (400, "stale_validation"))
        self.assertEqual(self.request(self.prefix + "overview")[1]["imports"][0]["adapter_version"], 1)

    def test_complete_error_download_and_bad_requests_never_import(self):
        payload = dict(self.payload, content=encoded("order_id,amount,channel\n" + "\n".join(f"A{i},bad,x" for i in range(61))))
        status, checked = self.request(self.prefix + "validate-import", dict(payload, page=3, page_size=25))
        self.assertEqual((status, checked["error_count"], len(checked["errors"])), (200, 61, 11))
        status, csv = self.request(self.prefix + "import-errors", payload)
        self.assertEqual(status, 200)
        self.assertTrue(csv.startswith(b"\xef\xbb\xbf"))
        self.assertIn("62,", csv.decode("utf-8-sig"))
        for extra in ({"page": "1"}, {"page_size": 101}, {"mapping": {}}):
            self.assertEqual(self.request(self.prefix + "validate-import", dict(payload, **extra))[0], 400)
        self.assertEqual(self.request(self.prefix + "overview")[1]["imports"], [])

    def test_session_origin_and_batch_scoping_apply_to_validation_and_download(self):
        for endpoint in ("validate-import", "import-errors"):
            for headers in ({"X-LedgerDesk-Token": "wrong"}, {"Origin": "https://external.invalid"}):
                self.assertEqual(self.request(self.prefix + endpoint, self.payload, headers)[0], 403)
        checked = self.request(self.prefix + "validate-import", self.payload)[1]
        other = self.request("/api/batches", {"name": "other"})[1]["batch_id"]
        status, error = self.request(f"/api/batches/{other}/import", dict(self.payload, receipt=checked["receipt"]))
        self.assertEqual((status, error["code"]), (400, "stale_validation"))
