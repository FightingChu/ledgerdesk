"""Regression coverage for the 0.1.1 handoff defects."""
import base64
from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from ledgerdesk import __main__ as cli
from ledgerdesk import __version__
from ledgerdesk.imports import InputError, parse, preview
from ledgerdesk.server import create_demo, make_server
from ledgerdesk.store import Store
from scripts import build_release


def encoded(text):
    return base64.b64encode(text.encode()).decode()


class CurrencyTests(unittest.TestCase):
    def check_csv(self, columns, values):
        data = encoded(f"order_id,amount,channel{columns}\nA,1.00,x{values}\n")
        info = preview("orders", data)
        return info, lambda: parse("orders", data, info["mapping"])

    def test_headers_and_cny_aliases(self):
        for header in ("currency", "Currency", "CURRENCY", "币种", "货币", "货币种类", "currency_code"):
            for value in ("CNY", "rmb", " 人民币 "):
                with self.subTest(header=header, value=value):
                    info, run = self.check_csv("," + header, "," + value)
                    self.assertTrue(info["currency"]["valid"])
                    self.assertFalse(info["currency"]["defaulted"])
                    self.assertEqual(run()[1][0]["amount_cents"], 100)

    def test_unknown_blank_and_conflicting_columns_rejected(self):
        for columns, values in ((",Currency", ",USD"), (",币种", ","),
                                (",currency_code", ",XYZ"), (",Currency,币种", ",CNY,USD"),
                                (",Currency,currency", ",CNY,")):
            with self.subTest(columns=columns, values=values):
                info, run = self.check_csv(columns, values)
                self.assertFalse(info["currency"]["valid"])
                self.assertEqual(info["currency"]["errors"][0]["line"], 2)
                with self.assertRaises(InputError):
                    run()

    def test_equivalent_columns_and_missing_currency(self):
        info, run = self.check_csv(",Currency,币种", ",CNY,RMB")
        self.assertTrue(info["currency"]["valid"])
        run()
        info, run = self.check_csv("", "")
        self.assertTrue(info["currency"]["defaulted"])
        self.assertEqual(info["currency"]["effective"], "CNY")
        run()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "currency.sqlite3"
            store = Store(path)
            batch = store.create_batch("currency policy persistence")
            for suffix, values in ((",Currency,币种", ",CNY,RMB"), ("", "")):
                data = encoded(f"order_id,amount,channel{suffix}\nA,1.00,x{values}\n")
                store.import_file(batch, "orders", "cny.csv", data, preview("orders", data)["mapping"])
            self.assertEqual([item["currency_policy"] for item in Store(path).detail(batch)["imports"]],
                             ["explicit_cny", "default_cny"])

    def test_mixed_currency_after_preview_rows_blocks_whole_file(self):
        text = "order_id,amount,channel,Currency\n" + "A,1,x,CNY\n" * 5 + "B,1,x,USD\n"
        data = encoded(text)
        info = preview("orders", data)
        self.assertIn("USD", info["currency"]["values"])
        self.assertEqual(info["currency"]["errors"][0]["line"], 7)
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "test.sqlite3")
            batch = store.create_batch("currency regression")
            with self.assertRaises(InputError):
                store.import_file(batch, "orders", "mixed.csv", data, info["mapping"])
            self.assertEqual(store.detail(batch)["imports"], [])


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ledgerdesk.sqlite3"

    def legacy(self):
        # Build the exact schema from the initial committed source, retained as a fixture.
        schema = (Path(__file__).parent / "fixtures" / "schema_v1.sql").read_text(encoding="utf-8")
        with closing(sqlite3.connect(self.path)) as con:
            con.executescript(schema)

    def version(self, path=None):
        with closing(sqlite3.connect(path or self.path)) as con:
            return con.execute("PRAGMA user_version").fetchone()[0]

    def test_new_database_and_reopen(self):
        store = Store(self.path)
        batch = create_demo(store)
        self.assertEqual(self.version(), 5)
        self.assertEqual(Store(self.path).detail(batch)["run"]["summary"]["issues"], 5)
        self.assertEqual(list(self.path.parent.glob("*.pre-*.sqlite3")), [])

    def test_legacy_upgrade_backup_and_preserve_import(self):
        self.legacy()
        with closing(sqlite3.connect(self.path)) as con:
            con.execute("INSERT INTO batches VALUES('old','legacy','retained',0,'2026-10-18')")
            con.execute("INSERT INTO imports VALUES('file','old','orders','old.csv','hash','{}',1,'2026-10-18')")
            con.commit()
        store = Store(self.path)
        self.assertEqual(self.version(), 5)
        self.assertEqual(store.detail("old")["imports"][0]["currency_policy"], "legacy_unverified")
        backups = list(self.path.parent.glob("*.pre-*.sqlite3"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.version(backups[0]), 1)
        Store(self.path)
        self.assertEqual(len(list(self.path.parent.glob("*.pre-*.sqlite3"))), 1)

    def test_migration_failure_rolls_back_schema_and_version(self):
        self.legacy()
        def broken(store, con, version):
            con.execute("CREATE TABLE partial(value TEXT)")
            con.execute("ALTER TABLE imports ADD COLUMN partial TEXT")
            raise sqlite3.OperationalError("injected migration failure")
        with patch.object(Store, "_migrate", broken), self.assertRaises(sqlite3.OperationalError):
            Store(self.path)
        self.assertEqual(self.version(), 1)
        with closing(sqlite3.connect(self.path)) as con:
            self.assertIsNone(con.execute("SELECT name FROM sqlite_master WHERE name='partial'").fetchone())
            self.assertNotIn("partial", [row[1] for row in con.execute("PRAGMA table_info(imports)")])
        self.assertEqual(self.version(list(self.path.parent.glob("*.pre-*.sqlite3"))[0]), 1)

    def test_backup_failure_prevents_migration(self):
        self.legacy()
        before = self.path.read_bytes()
        with patch.object(Store, "backup", side_effect=OSError("disk full")), self.assertRaises(OSError):
            Store(self.path)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.version(), 1)

    def test_future_version_rejected_without_modification(self):
        with closing(sqlite3.connect(self.path)) as con:
            con.executescript("CREATE TABLE future(value); INSERT INTO future VALUES('keep'); PRAGMA user_version=9;")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(InputError, "版本"):
            Store(self.path)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.version(), 9)
        self.assertEqual(len(list(self.path.parent.iterdir())), 1)

    def test_unversioned_nonempty_database_is_not_adopted(self):
        with closing(sqlite3.connect(self.path)) as con:
            con.execute("CREATE TABLE unrelated(value)")
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        with self.assertRaises(InputError):
            Store(self.path)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)


class ReleaseTests(unittest.TestCase):
    def test_release_excludes_unlisted_private_and_temporary_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in build_release.RELEASE_FILES:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((build_release.ROOT / name).read_bytes())
            (root / "samples/private.csv").write_text("synthetic private canary")
            (root / "debug.py").write_text("temporary reproduction")
            with patch.object(build_release, "ROOT", root), patch("sys.stdout", new_callable=io.StringIO):
                build_release.main()
            manifest = json.loads((root / "dist/release.json").read_text())
            with zipfile.ZipFile(root / "dist" / manifest["archive"]) as archive:
                self.assertNotIn("LedgerDesk/samples/private.csv", archive.namelist())
                self.assertNotIn("LedgerDesk/debug.py", archive.namelist())
                self.assertIn("LedgerDesk/tests/fixtures/schema_v1.sql", archive.namelist())


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "ledgerdesk.sqlite3"

    def invoke(self, response, *extra):
        with patch.object(sys, "argv", ["ledgerdesk", "--data-dir", self.temp.name, "--open", *extra]), \
             patch.object(cli, "urlopen", return_value=io.BytesIO(json.dumps(response).encode())), \
             patch.object(cli.webbrowser, "open") as browser, \
             patch.object(cli, "make_server", side_effect=OSError("address already in use")) as make:
            try:
                result = cli.main()
            except SystemExit:
                browser.assert_not_called()
                raise
            return browser, make, result

    def test_same_workspace_reuses_identified_instance(self):
        from ledgerdesk.server import instance_identity
        browser, make, _ = self.invoke({**instance_identity(self.db), "version": __version__})
        browser.assert_called_once()
        make.assert_not_called()

    def test_other_workspace_conflict_never_opens_page(self):
        from ledgerdesk.server import instance_identity
        with self.assertRaises(SystemExit) as exc:
            self.invoke({**instance_identity(self.db.parent / "other.sqlite3"), "version": __version__})
        self.assertEqual(exc.exception.code, 1)
        self.assertFalse(self.db.exists())

    def test_similar_json_and_nonobject_json_do_not_reuse(self):
        for payload in ({"version":"0.1.0", "batches":[], "reason_labels":{}}, [], None):
            with self.subTest(payload=payload):
                with self.assertRaises(SystemExit) as exc:
                    self.invoke(payload)
                self.assertEqual(exc.exception.code, 1)

    def test_older_release_requires_restart_and_never_opens_page(self):
        from ledgerdesk.server import instance_identity
        with self.assertRaises(SystemExit) as result:
            self.invoke({**instance_identity(self.db), "version": "0.4.0"})
        self.assertEqual(result.exception.code, 1)

    def test_occupied_port_does_not_create_requested_database(self):
        server = make_server(self.db, 0)
        self.addCleanup(server.server_close)
        other = self.db.parent / "other" / "ledgerdesk.sqlite3"
        with self.assertRaises(OSError):
            make_server(other, server.server_address[1])
        self.assertFalse(other.exists())

    def test_backup_cli_and_start_without_open(self):
        Store(self.db)
        with patch.object(sys, "argv", ["ledgerdesk", "--data-dir", self.temp.name, "--backup", str(self.db.parent / "copy.sqlite3")]), \
             patch.object(cli, "urlopen") as probe:
            cli.main()
            probe.assert_not_called()
        self.assertTrue((self.db.parent / "copy.sqlite3").exists())
        with patch.object(sys, "argv", ["ledgerdesk", "--data-dir", self.temp.name, "--port", "0"]), \
             patch.object(cli, "urlopen") as probe, patch.object(cli, "make_server") as make:
            make.return_value.server_address = ("127.0.0.1", 12345)
            cli.main()
            make.return_value.serve_forever.assert_called_once()
            make.return_value.server_close.assert_called_once()
            probe.assert_not_called()
