"""Architecture checks detect a nested violation and migration verification uses a copy."""
from scripts.check_boundaries import check
from scripts.check_migration import verify
from tests.support.workspace import WorkspaceTest


class DeveloperGateTests(WorkspaceTest):
    def test_boundary_gate_catches_nested_infrastructure_import(self):
        folder = self.root / "domain" / "nested"; folder.mkdir(parents=True)
        (folder / "bad.py").write_text("import sqlite3\n")
        self.assertEqual(check(self.root / "domain"), ["nested/bad.py"])

    def test_migration_check_preserves_source_rows(self):
        self.pair(count=1)
        before = self.store.detail(self.batch)
        report = verify(self.store.path)
        self.assertTrue(report["preserved_original_columns"])
        self.assertEqual(report["status"], "ok")
        self.assertEqual(self.store.detail(self.batch), before)
