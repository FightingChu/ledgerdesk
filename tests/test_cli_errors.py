"""CLI errors do not create missing workspaces or overwrite reports."""
import io
from unittest.mock import patch
from ledgerdesk import __main__ as cli
from tests.support.workspace import WorkspaceTest


class CliErrorTests(WorkspaceTest):
    def fails(self, *args):
        with patch("sys.argv", ["ledgerdesk", "--data-dir", str(self.root), *args]), patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit) as error:
            cli.main()
        self.assertNotEqual(error.exception.code, 0)

    def test_read_command_refuses_missing_database(self):
        self.fails("batches", "list")
        self.assertFalse((self.root / "ledgerdesk.sqlite3").exists())

    def test_existing_output_and_unknown_rule_are_preserved(self):
        self.pair(count=1); self.store.backup(self.root / "ledgerdesk.sqlite3")
        path = self.root / "existing.csv"; path.write_bytes(b"keep")
        self.fails("report", self.batch, "--out", str(path))
        self.assertEqual(path.read_bytes(), b"keep")
        self.fails("rules", "select", self.batch, "missing")
