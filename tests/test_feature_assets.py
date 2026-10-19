"""Every shipped workbench module is public, with traversal outside the asset allowlist denied."""
from ledgerdesk.http.assets import ASSETS
from tests.support.http import HttpWorkspaceTest


class FeatureAssetTests(HttpWorkspaceTest):
    def test_expanded_assets_and_unknown_files(self):
        for name in ASSETS:
            with self.subTest(name=name):
                status, content, headers = self.request("/" + name)
                self.assertEqual(status, 200)
                self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
                self.assertTrue(content)
        self.assertEqual(self.request("/runtime/worker.py")[0], 404)
        self.assertEqual(self.request("/../data/ledgerdesk.sqlite3")[0], 404)
