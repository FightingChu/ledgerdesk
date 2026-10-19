"""Business CLI commands share the same rules, reports and task services."""
import io
import json
from unittest.mock import patch
from ledgerdesk import __main__ as cli
from tests.support.workspace import WorkspaceTest


class CliCommandTests(WorkspaceTest):
    def command(self, *args):
        with patch("sys.argv", ["ledgerdesk", "--data-dir", str(self.root), *args]), patch("sys.stdout", new_callable=io.StringIO) as output:
            cli.main()
        return json.loads(output.getvalue())

    def test_batch_statistics_report_and_audit(self):
        # CLI uses the conventional database name, so make an independent backup of the test workspace.
        self.pair(count=2); self.store.backup(self.root / "ledgerdesk.sqlite3")
        self.assertEqual(self.command("batches", "list")["batches"][0]["id"], self.batch)
        self.assertEqual(self.command("stats", self.batch)["totals"]["groups"], 2)
        path = self.root / "cli.csv"
        self.command("report", self.batch, "--out", str(path))
        self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertGreater(self.command("audit", self.batch)["total"], 0)

    def test_queue_worker_and_rule_commands(self):
        self.pair(count=1); self.store.backup(self.root / "ledgerdesk.sqlite3")
        rule = self.command("rules", "create", "synthetic", "--tolerance-cents", "1")
        self.command("rules", "select", self.batch, rule["id"])
        job = self.command("jobs", "submit", "reconcile", "--batch-id", self.batch)
        self.assertEqual(self.command("jobs", "work", "--once")["processed"], 1)
        self.assertEqual(self.command("jobs", "get", job["id"])["state"], "succeeded")
