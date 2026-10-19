"""Feature routes call real shared services and preserve old localhost APIs."""
from tests.support.http import HttpWorkspaceTest


class FeatureHttpTests(HttpWorkspaceTest):
    def test_rule_statistics_and_evidence_endpoints(self):
        row = self.pair(count=1)[0]
        status, rule, _ = self.request("/api/rules", {"name": "HTTP policy", "tolerance_cents": 100})
        self.assertEqual(status, 200)
        self.assertEqual(self.request(f"/api/batches/{self.batch}/rule", {"rule_id": rule["id"]})[0], 200)
        self.store.reconcile(self.batch)
        status, stats, _ = self.request(f"/api/batches/{self.batch}/statistics")
        self.assertEqual((status, stats["totals"]["reasons"]["within_tolerance"]), (200, 1))
        path = f"/api/batches/{self.batch}/cases/{row['case_key']}"
        self.assertNotIn("rows", self.request(path + "/info")[1]["item"])
        self.assertEqual(self.request(path + "/evidence?page_size=1")[1]["total"], 2)

    def test_saved_filter_conflict_and_workspace_scope(self):
        status, preset, _ = self.request("/api/filters", {"name": "HTTP filter", "payload": {"q": "A"}})
        self.assertEqual(status, 200)
        self.assertEqual(self.request("/api/filters", {"name": "HTTP filter", "payload": {}})[0], 400)
        self.assertEqual(self.request("/api/workspace")[1]["total"], 1)
