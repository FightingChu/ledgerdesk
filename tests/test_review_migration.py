"""v6 upgrade preserves original columns, evidence, audits and snapshots."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from ledgerdesk.domain.filters import ResultFilter
from ledgerdesk.persistence.diagnostics import inspect_database
from ledgerdesk.server import create_demo
from ledgerdesk.store import Store


class ReviewMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Store(Path(self.temp.name) / "source.sqlite3")
        self.batch = create_demo(self.source)
        row = self.source.result_page(self.batch, ResultFilter(group="issues"))["items"][0]
        self.source.review(self.batch, row["case_key"], row["evidence_sha256"], "resolved", "retain synthetic note")
        self.path = Path(self.temp.name) / "v6.sqlite3"
        self.original = {}
        with self.source.connect() as source, closing(sqlite3.connect(self.path)) as target:
            target.executescript((Path(__file__).parent / "fixtures/schema_v6.sql").read_text(encoding="utf-8"))
            tables = [r[0] for r in target.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for table in tables:
                columns = ",".join(r[1] for r in target.execute("PRAGMA table_info(" + table + ")"))
                rows = [tuple(r) for r in source.execute("SELECT " + columns + " FROM " + table + " ORDER BY rowid")]
                if rows:
                    target.executemany("INSERT INTO " + table + " VALUES(" + ",".join("?" for _ in rows[0]) + ")", rows)
                self.original[table] = (columns, rows)
            target.commit()

    def test_upgrade_preserves_every_original_column_and_initializes_review_revision(self):
        self.assertEqual(inspect_database(self.path)["status"], "ok")
        upgraded = Store(self.path)
        backups = list(self.path.parent.glob("v6.sqlite3.pre-v6-to-v8-*.sqlite3"))
        self.assertEqual(len(backups), 1)
        with upgraded.connect() as con, closing(sqlite3.connect(backups[0])) as backup:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 8)
            self.assertEqual(backup.execute("PRAGMA user_version").fetchone()[0], 6)
            for table, (columns, rows) in self.original.items():
                self.assertEqual([tuple(r) for r in con.execute("SELECT " + columns + " FROM " + table + " ORDER BY rowid")], rows)
            self.assertEqual(con.execute("SELECT revision FROM reviews").fetchone()[0], 1)
            self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])
        current = upgraded.result_page(self.batch, ResultFilter(status="resolved"))["items"][0]
        self.assertEqual((current["note"], current["review_revision"]), ("retain synthetic note", 1))
        self.assertEqual(inspect_database(self.path)["status"], "ok")

    def test_upgrade_failure_rolls_back_column_indexes_version_and_rows(self):
        migrate = Store._migrate
        def broken(store, con, version):
            migrate(store, con, version)
            if version == 6:
                raise sqlite3.OperationalError("synthetic failure after indexes")
        with patch.object(Store, "_migrate", broken), self.assertRaises(sqlite3.OperationalError):
            Store(self.path)
        with closing(sqlite3.connect(self.path)) as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 6)
            self.assertNotIn("revision", [r[1] for r in con.execute("PRAGMA table_info(reviews)")])
            self.assertIsNone(con.execute("SELECT name FROM sqlite_master WHERE name='audit_batch_events'").fetchone())
            for table, (columns, rows) in self.original.items():
                self.assertEqual(con.execute("SELECT " + columns + " FROM " + table + " ORDER BY rowid").fetchall(), rows)
        self.assertEqual(inspect_database(self.path)["schema_version"], 6)
