"""Read-only preflight, exact input approvals, whole-file rollback and schema preservation."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from ledgerdesk.application.import_validation import ImportValidationService
from ledgerdesk.application.imports import ImportService
from ledgerdesk.domain.errors import InputError
from ledgerdesk.store import Store
from tests.test_ingestion import encoded


class ImportValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "input.sqlite3")
        self.batch = self.store.create_batch("synthetic preflight")
        self.service = ImportValidationService(self.store)
        self.payload = {"side": "orders", "filename": "synthetic.csv", "content": encoded("order_id,amount,channel,other\n0001,2,微信,3\n"),
                        "mapping": {"order_id": "order_id", "amount": "amount", "channel": "channel"},
                        "channel_aliases": {"微信": "wechat"}, "adapter_id": "standard_csv", "adapter_version": 1}

    def confirm(self, payload, receipt):
        return ImportService(self.store).add(self.batch, payload["side"], payload["filename"], payload["content"], payload["mapping"],
            payload.get("replace_id"), payload.get("reason", ""), payload.get("channel_aliases"),
            payload.get("adapter_id", "standard_csv"), payload.get("adapter_version", 1), receipt, self.service.approvals)

    def test_valid_preflight_does_not_write_then_confirmation_saves_adapter_and_alias(self):
        before = self.store.detail(self.batch)
        checked = self.service.check(self.batch, self.payload)
        self.assertEqual(self.store.detail(self.batch), before)
        self.assertTrue(checked["valid"])
        result = self.confirm(self.payload, checked["receipt"])
        with self.store.connect() as con:
            row = con.execute("SELECT adapter_id,adapter_version FROM imports WHERE id=?", (result["id"],)).fetchone()
            self.assertEqual(tuple(row), ("standard_csv", 1))
            self.assertEqual(tuple(con.execute("SELECT order_id,source_channel,channel FROM entries").fetchone()), ("0001", "微信", "wechat"))

    def test_any_effective_input_change_invalidates_receipt(self):
        checked = self.service.check(self.batch, self.payload)
        variants = [dict(self.payload, filename="different.csv"), dict(self.payload, channel_aliases={"微信": "wx"}),
                    dict(self.payload, mapping=dict(self.payload["mapping"], amount="other")),
                    dict(self.payload, content=encoded("order_id,amount,channel,other\n0002,2,微信,3\n"))]
        for payload in variants:
            with self.subTest(payload=payload), self.assertRaises(InputError) as error:
                self.confirm(payload, checked["receipt"])
            self.assertEqual(error.exception.code, "stale_validation")
        self.assertEqual(self.store.overview(self.batch)["imports"], [])

    def test_receipt_is_batch_scoped_expiring_signed_and_restart_scoped(self):
        checked = self.service.check(self.batch, self.payload)
        receipt = checked["receipt"]
        for value in ("", "not a receipt", receipt[:-1] + ("1" if receipt[-1] != "1" else "2"), True, "x" * 1025):
            with self.subTest(value=value), self.assertRaises(InputError):
                self.confirm(self.payload, value)
        with patch("ledgerdesk.application.import_validation.time.time", return_value=10**12), self.assertRaises(InputError):
            self.confirm(self.payload, receipt)
        old_batch = self.batch
        self.batch = self.store.create_batch("another")
        with self.assertRaises(InputError):
            self.confirm(self.payload, receipt)
        self.batch = old_batch
        self.service = ImportValidationService(self.store)
        with self.assertRaises(InputError):
            self.confirm(self.payload, receipt)

    def test_batch_change_archive_and_retry_reject_before_writing(self):
        receipt = self.service.check(self.batch, self.payload)["receipt"]
        self.store.update_batch(self.batch, archived=True)
        with self.assertRaises(InputError):
            self.confirm(self.payload, receipt)
        self.store.update_batch(self.batch, archived=False)
        self.confirm(self.payload, receipt)
        before = self.store.detail(self.batch)
        with self.assertRaises(InputError) as error:
            self.confirm(self.payload, receipt)
        self.assertEqual(error.exception.code, "stale_validation")
        self.assertEqual(self.store.detail(self.batch), before)

    def test_full_error_pages_download_and_failed_direct_import_have_no_side_effects(self):
        payload = dict(self.payload, content=encoded("order_id,amount,channel\n" + "\n".join(f"A{i},bad,x" for i in range(101))))
        before = self.store.detail(self.batch)
        result = self.service.check(self.batch, dict(payload, page=5, page_size=25))
        self.assertEqual((result["error_count"], len(result["errors"]), result["total_pages"]), (101, 1, 5))
        self.assertIsNone(result["receipt"])
        self.assertIn("102,", self.service.check(self.batch, payload, download=True).decode("utf-8-sig"))
        with self.assertRaises(InputError):
            self.confirm(payload, None)
        self.assertEqual(self.store.detail(self.batch), before)

    def test_replacement_reason_bound_and_failure_keeps_original_active(self):
        original = self.confirm(self.payload, self.service.check(self.batch, self.payload)["receipt"])
        replacement = dict(self.payload, replace_id=original["id"], reason="synthetic correction",
                           content=encoded("order_id,amount,channel,other\n0001,3,微信,4\n"))
        receipt = self.service.check(self.batch, replacement)["receipt"]
        with self.assertRaises(InputError):
            self.confirm(dict(replacement, reason="changed reason"), receipt)
        self.assertTrue(self.store.overview(self.batch)["imports"][0]["is_active"])
        with patch.object(self.store, "import_backup", side_effect=OSError("synthetic backup failure")), self.assertRaises(OSError):
            self.confirm(replacement, receipt)
        self.assertEqual(len(self.store.overview(self.batch)["imports"]), 1)
        self.confirm(replacement, receipt)
        self.assertEqual(sum(r["is_active"] for r in self.store.overview(self.batch)["imports"]), 1)

    def test_invalid_page_and_mapping_are_rejected_before_any_receipt(self):
        for extra in ({"page": 0}, {"page_size": 101}, {"page": True}, {"mapping": {}}, {"adapter_version": 99}, {"channel_aliases": []}):
            with self.subTest(extra=extra), self.assertRaises(InputError):
                self.service.check(self.batch, dict(self.payload, **extra))

    def test_v7_migration_preserves_original_columns_and_marks_old_adapter_version_unknown(self):
        self.confirm(self.payload, self.service.check(self.batch, self.payload)["receipt"])
        path = Path(self.temp.name) / "old.sqlite3"
        expected = {}
        with self.store.connect() as source, closing(sqlite3.connect(path)) as target:
            target.executescript((Path(__file__).parent / "fixtures/schema_v7.sql").read_text(encoding="utf-8"))
            for (table,) in target.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
                columns = ",".join(r[1] for r in target.execute("PRAGMA table_info(" + table + ")"))
                rows = [tuple(r) for r in source.execute("SELECT " + columns + " FROM " + table + " ORDER BY rowid")]
                if rows:
                    target.executemany("INSERT INTO " + table + " VALUES(" + ",".join("?" for _ in rows[0]) + ")", rows)
                expected[table] = (columns, rows)
            target.commit()
        migrate = Store._migrate
        def broken(store, con, version):
            migrate(store, con, version)
            if version == 7:
                raise sqlite3.OperationalError("synthetic schema failure")
        with patch.object(Store, "_migrate", broken), self.assertRaises(sqlite3.OperationalError):
            Store(path)
        with closing(sqlite3.connect(path)) as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 7)
            self.assertNotIn("adapter_id", [r[1] for r in con.execute("PRAGMA table_info(imports)")])
        migrated = Store(path)
        with migrated.connect() as con:
            for table, (columns, rows) in expected.items():
                self.assertEqual([tuple(r) for r in con.execute("SELECT " + columns + " FROM " + table + " ORDER BY rowid")], rows)
            self.assertIsNone(con.execute("SELECT adapter_version FROM imports").fetchone()[0])
            self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])
