"""All nested domain modules remain independent of infrastructure."""
import ast
from pathlib import Path
import unittest


class DependencyBoundaryTests(unittest.TestCase):
    def test_domain_packages_do_not_import_storage_or_http(self):
        root = Path(__file__).resolve().parent.parent / "ledgerdesk/domain"
        for path in root.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom):
                    names = (node.module or "").split(".")
                    self.assertFalse(set(names) & {"sqlite3", "http", "persistence", "application", "server"}, path)
                elif isinstance(node, ast.Import):
                    self.assertFalse(any(name.name.split(".")[0] in ("sqlite3", "http") for name in node.names), path)
