"""Reliability and source-lifecycle regression cases, using synthetic inputs only."""
import base64
from contextlib import closing
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from ledgerdesk import __main__ as cli
from ledgerdesk.imports import InputError, parse, preview
from ledgerdesk.server import create_demo, export_csv
from ledgerdesk.store import Store


def encoded(text):
    return base64.b64encode(text.encode()).decode()


class ManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ledgerdesk.sqlite3"
        self.store = Store(self.path)
        self.batch = self.store.create_batch("synthetic import management")

    def add(self, side, rows, **kwargs):
        headers = "order_id,amount,channel" if side == "orders" else "order_id,transaction_id,amount,event_type,channel"
        data = encoded(headers + "\n" + rows + "\n")
        return self.store.import_file(self.batch, side, side + ".csv", data, preview(side, data)["mapping"], **kwargs)

    def reconcile(self):
        self.store.reconcile(self.batch)
        return self.store.detail(self.batch)

    def resolve(self, order="A"):
        row = next(row for row in self.reconcile()["results"] if row["order_id"] == order)
        self.store.review(self.batch, row["case_key"], row["evidence_sha256"], "resolved", "synthetic checked")
        return row

    def test_cross_order_duplicate_resets_review_and_exposes_other_source(self):
        self.add("orders", "A,2,x\nB,1,x\nC,2,x")
        self.add("payments", "A,P1,1,sale,x\nC,P3,1,sale,x")
        before = self.resolve()
        self.resolve("C")
        extra = self.add("payments", "B,P1,1,sale,x")
        detail = self.reconcile()
        rows = {row["order_id"]: row for row in detail["results"]}
        self.assertIn("duplicate_transaction", rows["A"]["reasons"])
        self.assertEqual(rows["A"]["review_status"], "pending")
        self.assertNotEqual(rows["A"]["evidence_sha256"], before["evidence_sha256"])
        self.assertEqual(rows["A"]["duplicate_rows"][0]["order_id"], "B")
        self.assertEqual(rows["C"]["review_status"], "resolved")
        self.store.revoke_import(self.batch, extra["id"], "synthetic correction")
        # Returning to old source bytes must not resurrect an earlier resolved state.
        rows = {row["order_id"]: row for row in self.reconcile()["results"]}
        self.assertEqual(rows["A"]["review_status"], "pending")

    def test_revoke_preserves_evidence_and_blocks_stale_export(self):
        original = self.add("orders", "A,2,x")
        self.add("payments", "A,P1,1,sale,x")
        before = self.resolve()
        self.store.revoke_import(self.batch, original["id"], "wrong file")
        detail = self.store.detail(self.batch)
        self.assertTrue(detail["stale"])
        self.assertEqual(detail["imports"][0]["is_active"], 0)
        with self.assertRaises(InputError):
            export_csv(detail)
        with self.assertRaises(InputError):
            self.store.review(self.batch, before["case_key"], before["evidence_sha256"], "resolved", "stale")
        with self.store.connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM entries").fetchone()[0], 2)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 1)
        backups = list(self.path.parent.glob("*.before-import-*.sqlite3"))
        self.assertEqual(len(backups), 1)
        with closing(sqlite3.connect(backups[0])) as con:
            self.assertEqual(con.execute("SELECT is_active FROM imports WHERE id=?", (original["id"],)).fetchone()[0], 1)

    def test_replace_is_atomic_and_old_source_is_excluded(self):
        original = self.add("orders", "A,2,x")
        self.add("payments", "A,P1,1,sale,x")
        self.resolve()
        replacement = self.add("orders", "A,1,x", replace_id=original["id"], reason="correct amount")
        detail = self.reconcile()
        self.assertEqual(detail["results"][0]["reasons"], ["matched"])
        self.assertEqual(detail["results"][0]["order_count"], 1)
        old = next(row for row in detail["imports"] if row["id"] == original["id"])
        new = next(row for row in detail["imports"] if row["id"] == replacement["id"])
        self.assertEqual(old["is_active"], 0)
        self.assertEqual(new["replaces_id"], old["id"])
        self.assertEqual(old["revoked_reason"], "correct amount")

    def test_failed_replacement_rolls_back_revocation_and_revision(self):
        original = self.add("orders", "A,2,x")
        with self.store.connect() as con:
            con.execute("CREATE TRIGGER reject_entries BEFORE INSERT ON entries BEGIN SELECT RAISE(ABORT,'injected failure'); END")
        revision = self.store.detail(self.batch)["batch"]["input_revision"]
        with self.assertRaises(sqlite3.IntegrityError):
            self.add("orders", "A,1,x", replace_id=original["id"], reason="correct amount")
        detail = self.store.detail(self.batch)
        self.assertEqual(len(detail["imports"]), 1)
        self.assertEqual(detail["imports"][0]["is_active"], 1)
        self.assertEqual(detail["batch"]["input_revision"], revision)

    def test_invalid_replacement_leaves_original_active(self):
        original = self.add("orders", "A,2,x")
        with self.assertRaises(InputError):
            self.add("orders", "A,invalid,x", replace_id=original["id"], reason="invalid")
        self.assertEqual(self.store.detail(self.batch)["imports"][0]["is_active"], 1)

    def test_reimport_revoked_bytes_and_replace_same_bytes_with_new_mapping(self):
        data = encoded("order_id,amount,alternative,channel\nA,2,1,x\n")
        mapping = preview("orders", data)["mapping"]
        old = self.store.import_file(self.batch, "orders", "original.csv", data, mapping)
        revised = dict(mapping, amount="alternative")
        new = self.store.import_file(self.batch, "orders", "corrected.csv", data, revised,
                                     replace_id=old["id"], reason="correct column")
        self.assertNotEqual(new["id"], old["id"])
        self.store.revoke_import(self.batch, new["id"], "undo")
        reimport = self.store.import_file(self.batch, "orders", "again.csv", data, mapping)
        self.assertNotEqual(reimport["id"], old["id"])
        with self.store.connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM imports WHERE is_active=1").fetchone()[0], 1)

    def test_wrong_scope_side_duplicate_and_repeated_revocation_rejected(self):
        original = self.add("orders", "A,2,x")
        other = self.add("orders", "B,1,x")
        another_batch = self.store.create_batch("another batch")
        with self.assertRaises(InputError):
            self.store.revoke_import(another_batch, original["id"], "wrong batch")
        with self.assertRaises(InputError):
            self.add("payments", "A,P1,1,sale,x", replace_id=original["id"], reason="wrong side")
        with self.assertRaises(InputError):
            self.add("orders", "B,1,x", replace_id=original["id"], reason="already active")
        with self.assertRaises(InputError):
            self.store.revoke_import(self.batch, other["id"], "")
        self.store.revoke_import(self.batch, other["id"], "undo")
        with self.assertRaises(InputError):
            self.store.revoke_import(self.batch, other["id"], "repeat")

    def test_backup_failure_prevents_revocation(self):
        original = self.add("orders", "A,2,x")
        with patch.object(Store, "backup", side_effect=OSError("disk full")), self.assertRaises(OSError):
            self.store.revoke_import(self.batch, original["id"], "undo")
        self.assertEqual(self.store.detail(self.batch)["imports"][0]["is_active"], 1)

    def test_undo_then_rerun_selects_new_run_and_preserves_unchanged_review(self):
        self.add("orders", "A,2,x")
        self.add("payments", "A,P1,1,sale,x")
        self.resolve()
        first = self.store.detail(self.batch)["run"]["id"]
        extra = self.add("orders", "B,1,x")
        second = self.reconcile()["run"]["id"]
        self.store.revoke_import(self.batch, extra["id"], "undo extra")
        third = self.reconcile()
        self.assertNotIn(third["run"]["id"], (first, second))
        self.assertFalse(third["stale"])
        self.assertEqual(third["results"][0]["review_status"], "resolved")
        self.assertTrue(self.store.reconcile(self.batch)["reused"])

    def test_version_two_upgrade_preserves_rows_and_requires_rerun(self):
        path = Path(self.temp.name) / "v2.sqlite3"
        fixture = (Path(__file__).parent / "fixtures/schema_v1.sql").read_text()
        with closing(sqlite3.connect(path)) as con:
            con.executescript(fixture + "\nALTER TABLE imports ADD COLUMN currency_policy TEXT NOT NULL DEFAULT 'legacy_unverified'; PRAGMA user_version=2;")
            con.execute("INSERT INTO batches VALUES('legacy','old','',0,'2026-10-18')")
            con.execute("INSERT INTO imports VALUES('file','legacy','orders','old.csv','hash','{}',1,'2026-10-18','default_cny')")
            con.execute("INSERT INTO entries VALUES(1,'file',2,'x','A','','expected',200)")
            con.commit()
        upgraded = Store(path)
        detail = upgraded.detail("legacy")
        self.assertEqual(detail["imports"][0]["currency_policy"], "default_cny")
        self.assertEqual(detail["imports"][0]["is_active"], 1)
        with upgraded.connect() as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 6)
            self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])
        with closing(sqlite3.connect(next(path.parent.glob("v2.sqlite3.pre-*.sqlite3")))) as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 2)

    def test_mapping_template_and_channel_alias_roundtrip(self):
        store = Store(self.path)
        batch = store.create_batch("template aliases")
        template = store.save_template("微信标准", "orders", {"order_id": "order_id", "amount": "amount", "channel": "channel"}, {"微信": "wechat"})
        self.assertEqual(json.loads(template["channel_aliases"]), {"微信": "wechat"})
        data = encoded("order_id,amount,channel\nA,1.00,微信\n")
        store.import_file(batch, "orders", "orders.csv", data, json.loads(template["mapping"]), channel_aliases=json.loads(template["channel_aliases"]))
        self.assertEqual(store.list_templates("orders")[0]["name"], "微信标准")
        self.assertEqual(store.detail(batch)["imports"][0]["channel_aliases"], '{"微信": "wechat"}')
        with store.connect() as con:
            self.assertEqual(con.execute("SELECT channel FROM entries").fetchone()[0], "wechat")
        self.assertTrue(store.delete_template(template["id"])["deleted"])

    def test_history_compare_and_filtered_export_rows(self):
        batch = self.store.create_batch("history")
        self.batch = batch
        self.add("orders", "A,1,x")
        self.add("payments", "A,P1,1,sale,x")
        first = self.reconcile()["run"]["id"]
        self.add("orders", "B,2,x")
        second = self.reconcile()["run"]["id"]
        comparison = self.store.compare_runs(batch, first, second)
        self.assertEqual(comparison["counts"]["added"], 1)
        self.assertEqual(len(self.store.history(batch)), 2)


class InputAndBackupTests(unittest.TestCase):
    def test_ambiguous_aliases_need_explicit_mapping(self):
        for columns in ("amount,Amount", "amount,金额"):
            data = encoded(f"order_id,{columns},channel\nA,100.00,1.00,x\n")
            info = preview("orders", data)
            self.assertEqual(info["mapping"]["amount"], "")
            self.assertEqual(len(info["ambiguous_fields"]["amount"]), 2)
            with self.assertRaises(InputError):
                parse("orders", data, info["mapping"])
            self.assertEqual(parse("orders", data, dict(info["mapping"], amount="amount"))[1][0]["amount_cents"], 10000)

    def test_backup_missing_source_does_not_create_directory_or_target(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "mistyped"
            target = Path(directory) / "backup.sqlite3"
            with patch.object(sys, "argv", ["ledgerdesk", "--data-dir", str(missing), "--backup", str(target)]), \
                 patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit) as exc:
                cli.main()
            self.assertEqual(exc.exception.code, 1)
            self.assertFalse(missing.exists())
            self.assertFalse(target.exists())

    def test_backup_old_database_does_not_migrate_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "old.sqlite3"
            fixture = (Path(__file__).parent / "fixtures/schema_v1.sql").read_text()
            with closing(sqlite3.connect(source)) as con:
                con.executescript(fixture)
                con.execute("INSERT INTO batches VALUES('old','test','',0,'2026-10-18')")
                con.commit()
            before = source.read_bytes()
            summary = Store.backup_existing(source, Path(directory) / "copy.sqlite3")
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(summary["batches"], 1)
            self.assertEqual(summary["schema_version"], 1)
