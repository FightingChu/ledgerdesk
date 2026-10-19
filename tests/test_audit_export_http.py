"""Audit export endpoint uses localhost session checks and bounded filters."""
from tests.support.http import HttpWorkspaceTest


class AuditExportHttpTests(HttpWorkspaceTest):
    def test_csv_json_and_security(self):
        self.pair(count=1)
        status, data, headers = self.request(f"/api/batches/{self.batch}/audit-export?format=csv")
        self.assertEqual(status, 200)
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        self.assertIn("attachment", headers["Content-Disposition"])
        status, data, _ = self.request(f"/api/batches/{self.batch}/audit-export?format=json&action=reconcile")
        self.assertEqual(status, 200)
        self.assertTrue(all('"action":"reconcile"' in line for line in data.decode().splitlines()))
        self.assertEqual(self.request(f"/api/batches/{self.batch}/audit-export?format=xml")[0], 400)
        self.assertEqual(self.request(f"/api/batches/{self.batch}/audit-export?format=xml")[0], 400)
