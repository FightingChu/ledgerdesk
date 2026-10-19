"""Version-required CLI review refuses stale replay."""
import io
import json
from unittest.mock import patch
from ledgerdesk import __main__ as cli
from tests.support.workspace import WorkspaceTest


class CliReviewTests(WorkspaceTest):
    def test_single_review_and_stale_retry(self):
        row = self.pair(count=1)[0]; self.store.backup(self.root / "ledgerdesk.sqlite3")
        args = ["ledgerdesk", "--data-dir", str(self.root), "reviews", "set", self.batch, row["case_key"],
                "--run-id", self.run, "--evidence", row["evidence_sha256"], "--revision", "0", "--status", "resolved", "--note", "CLI checked"]
        with patch("sys.argv", args), patch("sys.stdout", new_callable=io.StringIO) as output:
            cli.main()
        self.assertEqual(json.loads(output.getvalue())["count"], 1)
        with patch("sys.argv", args), patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit):
            cli.main()
