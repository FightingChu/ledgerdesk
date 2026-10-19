"""Data recovery contracts exercised against temporary synthetic databases."""
from contextlib import closing
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ledgerdesk import __main__ as cli
from ledgerdesk.domain.errors import InputError
from ledgerdesk.persistence.database import Database
from ledgerdesk.persistence.diagnostics import inspect_database
from ledgerdesk.application.data_management import DataManagementService, restore_database
from ledgerdesk.server import create_demo, make_server
from ledgerdesk.store import Store


class DataManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "data/ledgerdesk.sqlite3"
        self.store = Store(self.path)
        self.batch = create_demo(self.store)
        row = next(row for row in self.store.detail(self.batch)["results"] if row["order_id"] == "O1003")
        self.store.review(self.batch, row["case_key"], row["evidence_sha256"], "resolved", "synthetic private note")
        self.service = DataManagementService(self.path)

    def test_diagnostic_is_read_only_and_excludes_user_values(self):
        before = self.path.read_bytes()
        report = inspect_database(self.path)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["schema_version"], 8)
        self.assertEqual(report["counts"]["entries"], 15)
        self.assertEqual(self.path.read_bytes(), before)
        text = json.dumps(report, ensure_ascii=False)
        for sensitive in (str(self.root), "O1003", "synthetic private note", "样例", "orders.csv"):
            self.assertNotIn(sensitive, text)

    def test_missing_corrupt_foreign_and_future_databases_are_distinguished(self):
        missing = self.root / "missing/no.sqlite3"
        self.assertEqual(inspect_database(missing)["status"], "missing")
        self.assertFalse(missing.parent.exists())
        corrupt = self.root / "corrupt.sqlite3"
        corrupt.write_bytes(b"not sqlite")
        self.assertEqual(inspect_database(corrupt)["status"], "invalid")
        foreign = self.root / "foreign.sqlite3"
        with closing(sqlite3.connect(foreign)) as con:
            con.executescript("CREATE TABLE foreign_data(value); PRAGMA user_version=5;")
        self.assertEqual(inspect_database(foreign)["status"], "invalid")
        future = self.root / "future.sqlite3"
        with closing(sqlite3.connect(future)) as con:
            con.executescript("CREATE TABLE future(value); PRAGMA user_version=99;")
        original = future.read_bytes()
        self.assertEqual(inspect_database(future)["status"], "unsupported")
        self.assertEqual(future.read_bytes(), original)

    def test_foreign_key_violation_is_not_reported_healthy(self):
        with closing(sqlite3.connect(self.path)) as con:
            con.execute("INSERT INTO entries(import_id,line,channel,order_id,transaction_id,kind,amount_cents) VALUES('missing',2,'x','x','','expected',1)")
            con.commit()
        report = inspect_database(self.path)
        self.assertEqual(report["status"], "invalid")
        self.assertGreater(report["foreign_key_violations"], 0)

    def test_managed_backup_list_check_and_unique_names(self):
        self.assertEqual(self.service.list_backups(), [])
        self.assertFalse(self.service.backup_dir.exists())
        first = self.service.create_backup()
        second = self.service.create_backup()
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(len(self.service.list_backups()), 2)
        checked = self.service.verify_backup(first["id"])
        self.assertEqual(checked["status"], "ok")
        self.assertEqual(len(checked["sha256"]), 64)
        self.assertEqual(checked["counts"]["reviews"], 1)

    def test_backup_counts_and_pages_share_one_snapshot_during_writes(self):
        write_backup = Database._write_backup
        def concurrent_write(source, source_path, destination):
            self.store.create_batch("created after snapshot")
            write_backup(source, source_path, destination)
        target = self.root / "snapshot.sqlite3"
        with patch.object(Database, "_write_backup", side_effect=concurrent_write):
            summary = Database.backup_existing(self.path, target)
        self.assertEqual(summary["batches"], 1)
        self.assertEqual(len(self.store.list_batches()), 2)
        self.assertEqual(inspect_database(target)["counts"]["batches"], 1)

    def test_corrupted_managed_backup_cannot_create_restored_workspace(self):
        backup = self.service.create_backup()
        (self.service.backup_dir / backup["id"]).write_bytes(b"damaged")
        self.assertEqual(self.service.verify_backup(backup["id"])["status"], "invalid")
        with self.assertRaises(InputError):
            self.service.restore_backup(backup["id"], "damaged-restore")
        self.assertFalse(self.service.restore_dir.exists())

    def test_path_injection_and_unknown_backup_rejected(self):
        for name in ("../ledgerdesk.sqlite3", str(self.path), "missing.sqlite3", "", None, ["invalid"]):
            with self.subTest(name=name), self.assertRaises(InputError):
                self.service.verify_backup(name)
        backup = self.service.create_backup()
        for name in ("../escape", "a/b", "a\\b", "", ".", "..", None):
            with self.subTest(name=name), self.assertRaises(InputError):
                self.service.restore_backup(backup["id"], name)

    def test_restore_preserves_original_and_all_records_in_new_workspace(self):
        backup = self.service.create_backup()
        before = self.path.read_bytes()
        restored = self.service.restore_backup(backup["id"], "restored-test")
        destination = Path(restored["data_dir"]) / "ledgerdesk.sqlite3"
        self.assertEqual(self.path.read_bytes(), before)
        other = Store(destination)
        detail = other.detail(self.batch)
        self.assertEqual(detail["run"], self.store.detail(self.batch)["run"])
        self.assertEqual(next(r for r in detail["results"] if r["order_id"] == "O1003")["note"], "synthetic private note")
        self.assertFalse(detail["stale"])
        with self.assertRaises(InputError):
            self.service.restore_backup(backup["id"], "restored-test")

    def test_restore_never_overwrites_even_an_empty_existing_directory(self):
        destination = self.root / "already"
        destination.mkdir()
        with self.assertRaises(InputError):
            restore_database(self.path, destination)
        self.assertEqual(list(destination.iterdir()), [])

    def test_invalid_restore_does_not_create_target(self):
        bad = self.root / "bad.sqlite3"
        bad.write_bytes(b"invalid")
        with self.assertRaises(InputError):
            restore_database(bad, self.root / "restored")
        self.assertFalse((self.root / "restored").exists())

    def test_old_database_restore_keeps_version_until_normal_start(self):
        original = self.root / "v1.sqlite3"
        with closing(sqlite3.connect(original)) as con:
            con.executescript((Path(__file__).parent / "fixtures/schema_v1.sql").read_text(encoding="utf-8"))
        before = original.read_bytes()
        target = self.root / "restored-v1"
        result = restore_database(original, target)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(original.read_bytes(), before)
        with closing(sqlite3.connect(target / "ledgerdesk.sqlite3")) as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 1)
        Store(target / "ledgerdesk.sqlite3")

    def test_failed_restore_cleans_only_new_files(self):
        target = self.root / "failed"
        with patch.object(Database, "backup_existing", side_effect=OSError("disk full")), self.assertRaises(OSError):
            restore_database(self.path, target)
        self.assertFalse(target.exists())
        self.assertEqual(inspect_database(self.path)["status"], "ok")

    def test_restore_handles_unsupported_hardlinks_and_preserves_racing_files(self):
        target = self.root / "fallback"
        with patch("ledgerdesk.application.data_management.os.link", side_effect=OSError("not supported")):
            self.assertTrue(restore_database(self.path, target)["restored"])
        destination = self.root / "race"
        def race(source, target):
            Path(target).write_bytes(b"created by someone else")
            raise FileExistsError("target appeared")
        with patch("ledgerdesk.application.data_management.os.link", side_effect=race), self.assertRaises(InputError):
            restore_database(self.path, destination)
        self.assertEqual((destination / "ledgerdesk.sqlite3").read_bytes(), b"created by someone else")
        self.assertFalse(list(destination.glob(".restore-*")))

    def test_cli_diagnostics_and_restore_do_not_start_server(self):
        destination = self.root / "cli-restore"
        with patch.object(sys, "argv", ["ledgerdesk", "--data-dir", str(self.path.parent), "--diagnose"]), \
             patch("sys.stdout", new_callable=io.StringIO) as output, patch.object(cli, "make_server") as server, \
             patch.object(cli.logging, "basicConfig"):
            cli.main()
            self.assertEqual(json.loads(output.getvalue())["status"], "ok")
            server.assert_not_called()
        with patch.object(sys, "argv", ["ledgerdesk", "--restore", str(self.path), "--restore-to", str(destination)]), \
             patch("sys.stdout", new_callable=io.StringIO), patch.object(cli, "make_server") as server, \
             patch.object(cli.logging, "basicConfig"):
            cli.main()
            server.assert_not_called()
        self.assertTrue((destination / "ledgerdesk.sqlite3").exists())

    def test_diagnose_missing_source_returns_error_without_creating_database(self):
        missing = self.root / "missing"
        with patch.object(sys, "argv", ["ledgerdesk", "--data-dir", str(missing), "--diagnose"]), \
             patch("sys.stdout", new_callable=io.StringIO) as output, patch.object(cli.logging, "basicConfig"), \
             self.assertRaises(SystemExit) as result:
            cli.main()
        self.assertEqual(result.exception.code, 1)
        self.assertEqual(json.loads(output.getvalue())["status"], "missing")
        self.assertFalse(missing.exists())


class HttpDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "ledgerdesk.sqlite3"
        self.server = make_server(self.path, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.token = self.request("/api/bootstrap")[1]["token"]
        self.batch = self.request("/api/demo", {})[1]["batch_id"]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, payload=None, token=True):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-LedgerDesk-Token"] = getattr(self, "token", "")
        request = Request(self.url + path, None if payload is None else json.dumps(payload).encode(), headers)
        try:
            response = urlopen(request, timeout=20)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            result = json.loads(raw) if response.headers.get("Content-Type", "").startswith("application/json") else raw
            return response.status, result, response.headers

    def test_backup_verify_restore_and_private_diagnostic_export(self):
        self.assertEqual(self.request("/api/data")[1]["backups"], [])
        status, backup, _ = self.request("/api/data/backup", {})
        self.assertEqual(status, 200)
        self.assertEqual(backup["status"], "ok")
        self.assertEqual(len(self.request("/api/data")[1]["backups"]), 1)
        status, checked, _ = self.request("/api/data/verify", {"id": backup["id"]})
        self.assertEqual(status, 200)
        self.assertEqual(backup["sha256"], checked["sha256"])
        status, restored, _ = self.request("/api/data/restore", {"id": backup["id"], "workspace_name": "restored"})
        self.assertEqual(status, 200)
        self.assertTrue((Path(restored["data_dir"]) / "ledgerdesk.sqlite3").is_file())
        before = Store(self.path).detail(self.batch)
        self.assertEqual(Store(Path(restored["data_dir"]) / "ledgerdesk.sqlite3").detail(self.batch)["run"], before["run"])
        status, report, headers = self.request("/api/data/diagnostics/export")
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        text = json.dumps(report, ensure_ascii=False)
        self.assertNotIn(str(self.path.parent), text)
        self.assertNotIn("O1003", text)
        self.assertEqual(self.request("/data.js")[0], 200)

    def test_mutations_need_token_and_reject_arbitrary_paths(self):
        for route in ("backup", "verify", "restore"):
            self.assertEqual(self.request("/api/data/" + route, {}, token=False)[0], 403)
        status, error, _ = self.request("/api/data/verify", {"id": str(self.path)})
        self.assertEqual((status, error["code"]), (400, "invalid_backup"))
        backup = self.request("/api/data/backup", {})[1]
        status, error, _ = self.request("/api/data/restore", {"id": backup["id"], "workspace_name": "../escape"})
        self.assertEqual((status, error["code"]), (400, "invalid_path"))
