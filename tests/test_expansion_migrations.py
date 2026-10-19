"""v8 -> v10 materializations preserve every original business value."""
from contextlib import closing
from pathlib import Path
import sqlite3
from unittest.mock import patch
from ledgerdesk.store import Store
from ledgerdesk.persistence.diagnostics import inspect_database
from tests.support.workspace import WorkspaceTest


class ExpansionMigrationTests(WorkspaceTest):
    def old_copy(self):
        self.pair(count=3)
        path = self.root / "old.sqlite3"; expected = {}
        with self.store.connect() as source, closing(sqlite3.connect(path)) as target:
            target.executescript((Path(__file__).parent / "fixtures/schema_v8.sql").read_text(encoding="utf-8"))
            tables = [r[0] for r in target.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for table in tables:
                columns = ",".join(r[1] for r in target.execute("PRAGMA table_info(" + table + ")"))
                rows = [tuple(r) for r in source.execute("SELECT " + columns + " FROM " + table + " ORDER BY rowid")]
                if rows:
                    target.executemany("INSERT INTO " + table + " VALUES(" + ",".join("?" for _ in rows[0]) + ")", rows)
                expected[table] = columns, rows
            target.commit()
        return path, expected

    def test_preserves_original_rows_and_backfills_all_projections(self):
        path, expected = self.old_copy(); upgraded = Store(path)
        with upgraded.connect() as con:
            for table, (columns, rows) in expected.items():
                self.assertEqual([tuple(r) for r in con.execute("SELECT " + columns + " FROM " + table + " ORDER BY rowid")], rows)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM result_metrics").fetchone()[0], 3)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM result_sources").fetchone()[0], 6)
            self.assertIsNone(con.execute("SELECT rule_snapshot FROM runs").fetchone()[0])
        self.assertEqual(inspect_database(path)["status"], "ok")

    def test_failure_after_ddl_and_backfill_rolls_back_both_versions(self):
        path, expected = self.old_copy(); migrate = Store._migrate
        def broken(store, con, version):
            migrate(store, con, version)
            if version == 9:
                raise sqlite3.OperationalError("synthetic failure after job schema")
        with patch.object(Store, "_migrate", broken), self.assertRaises(sqlite3.OperationalError):
            Store(path)
        with closing(sqlite3.connect(path)) as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 8)
            self.assertIsNone(con.execute("SELECT name FROM sqlite_master WHERE name='jobs'").fetchone())
            self.assertIsNone(con.execute("SELECT name FROM sqlite_master WHERE name='result_metrics'").fetchone())
