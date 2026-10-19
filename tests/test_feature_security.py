"""Every new mutation keeps session and origin checks, and malformed payloads stay client errors."""
from tests.support.http import HttpWorkspaceTest


class FeatureSecurityTests(HttpWorkspaceTest):
    def test_new_mutations_require_current_session(self):
        for path in ("/api/rules", "/api/report-profiles", "/api/jobs", "/api/filters", "/api/backup-policy", "/api/backup-policy/prune"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path, {}, {"X-LedgerDesk-Token": "wrong"})[0], 403)
                self.assertEqual(self.request(path, {}, {"Origin": "https://external.invalid"})[0], 403)

    def test_invalid_feature_payloads_and_repeated_query_parameters_do_not_return_500(self):
        for path, value in (("/api/rules", {"name": [], "tolerance_cents": []}), ("/api/jobs", {"kind": []}),
                            ("/api/report-profiles", {"name": "bad", "columns": [None]}), ("/api/filters", {"name": "bad", "payload": []})):
            with self.subTest(path=path):
                self.assertEqual(self.request(path, value)[0], 400)
        self.assertEqual(self.request("/api/workspace?page=1&page=2")[0], 400)
