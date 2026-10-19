"""Report profiles and saved filters are usable from scripts without a web server."""
import io
import json
from unittest.mock import patch
from ledgerdesk import __main__ as cli
from tests.support.workspace import WorkspaceTest


class CliProfileTests(WorkspaceTest):
    def call(self, *args):
        with patch("sys.argv", ["ledgerdesk", "--data-dir", str(self.root), *args]), patch("sys.stdout", new_callable=io.StringIO) as output:
            cli.main()
        return json.loads(output.getvalue())

    def test_profiles_and_filters_round_trip(self):
        self.store.backup(self.root / "ledgerdesk.sqlite3")
        profile = self.call("profiles", "create", "compact", "--columns", "order_id,note")
        self.assertEqual(profile["columns"], ["order_id", "note"])
        preset = self.call("filters", "save", "open", '{"group":"issues"}')
        self.assertEqual(self.call("filters", "list")["filters"][0]["id"], preset["id"])
        self.call("filters", "delete", preset["id"], "--revision", "1")
        self.assertEqual(self.call("filters", "list")["filters"], [])
