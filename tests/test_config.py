"""Configuration validation must never create a workspace as a side effect."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from ledgerdesk import __main__ as cli
from ledgerdesk.config import Settings
from ledgerdesk.domain.errors import InputError


class ConfigTests(unittest.TestCase):
    def test_defaults_relative_paths_and_command_line_override(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / "config.json"
            file.write_text(json.dumps({"version": 1, "port": 9000, "data_dir": "missing", "open_browser": True}))
            settings = Settings.load(file, root / "default")
            self.assertEqual(settings.data_dir, (root / "missing").resolve())
            self.assertEqual(Settings.load(None, root / "default").port, 8765)
            with patch.object(sys, "argv", ["ledgerdesk", "--config", str(file), "--port", "0", "--no-open", "--check-config"]), \
                 patch("sys.stdout", new_callable=io.StringIO) as output, patch.object(cli, "make_server") as server, \
                 patch.object(cli.logging, "basicConfig"):
                cli.main()
                value = json.loads(output.getvalue())
                self.assertEqual(value["port"], 0)
                self.assertFalse(value["open_browser"])
                server.assert_not_called()
            self.assertFalse((root / "missing").exists())

    def test_bad_values_unknown_fields_and_future_versions_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "config.json"
            for config in ([], {"version": 2}, {"version": True}, {"version": 1, "port": True},
                           {"version": 1, "port": 70000}, {"version": 1, "data_dir": ""},
                           {"version": 1, "open_browser": "true"}, {"version": 1, "unknown": 1}):
                with self.subTest(config=config):
                    file.write_text(json.dumps(config))
                    with self.assertRaises(InputError) as error:
                        Settings.load(file, Path(directory) / "default")
                    self.assertEqual(error.exception.code, "invalid_config")
