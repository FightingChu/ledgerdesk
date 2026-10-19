"""Synthetic generation preserves existing folders and supplies valid standard inputs."""
import base64
import tempfile
from pathlib import Path
import unittest
from scripts.generate_synthetic import generate
from ledgerdesk.imports import preview, parse


class SyntheticToolTests(unittest.TestCase):
    def test_generation_and_non_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "new"
            self.assertEqual(generate(destination, 7)["groups"], 7)
            data = base64.b64encode((destination / "orders.csv").read_bytes()).decode()
            self.assertEqual(len(parse("orders", data, preview("orders", data)["mapping"])[1]), 7)
            with self.assertRaises(FileExistsError):
                generate(destination, 7)

    def test_file_limits_are_checked_before_creating_output(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "missing"
            with self.assertRaises(ValueError):
                generate(target, 10001)
            self.assertFalse(target.exists())
