"""HTTP reports stream complete content and reject stale inputs before headers."""
from tests.support.http import HttpWorkspaceTest
import base64
import json


class ReportHttpTests(HttpWorkspaceTest):
    def test_csv_and_html_have_security_headers_and_custom_columns(self):
        self.pair(count=110)
        profile = self.request("/api/report-profiles", {"name": "HTTP compact", "columns": ["order_id", "difference"]})[1]
        status, data, headers = self.request(f"/api/batches/{self.batch}/export?profile_id={profile['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(len(data.decode("utf-8-sig").splitlines()), 111)
        self.assertIn("attachment", headers["Content-Disposition"])
        manifest = json.loads(base64.urlsafe_b64decode(headers["X-LedgerDesk-Report"]))
        self.assertEqual(manifest["run_id"], self.run)
        self.assertEqual(manifest["columns"], ["order_id", "difference"])
        status, html, headers = self.request(f"/api/batches/{self.batch}/report?format=html")
        self.assertEqual(status, 200)
        self.assertIn(b"</html>", html)
        self.assertIn("sha256-", headers["Content-Security-Policy"])

    def test_missing_profile_and_stale_run_return_json_errors(self):
        self.pair(count=1)
        status, error, _ = self.request(f"/api/batches/{self.batch}/export?profile_id=missing")
        self.assertEqual((status, error["code"]), (400, "not_found"))
        self.add("orders", "order_id,amount,channel\nnew,1,x\n")
        self.assertEqual(self.request(f"/api/batches/{self.batch}/report")[0], 400)
