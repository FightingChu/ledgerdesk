"""The audit export CLI uses exclusive output and the same service as HTTP."""
import csv
import io
from pathlib import Path
from unittest.mock import patch
from ledgerdesk import __main__ as cli
from tests.support.workspace import WorkspaceTest


class AuditExportCliTests(WorkspaceTest):
    def test_export_command_creates_csv_without_overwrite(self):
        self.pair(count=1)
        self.store.backup(self.root / "ledgerdesk.sqlite3")
        output = self.root / "audit.csv"
        args = ["ledgerdesk", "--data-dir", str(self.root), "audit-export", self.batch, "--out", str(output)]
        with patch("sys.argv", args), patch("sys.stdout", new_callable=io.StringIO):
            cli.main()
        rows = list(csv.reader(io.StringIO(output.read_text(encoding="utf-8-sig"))))
        self.assertGreater(len(rows), 1)
        with patch("sys.argv", args), patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit):
            cli.main()
