"""Workflow regressions for 0.4, using synthetic data and isolated databases."""
import base64
from contextlib import closing
import csv
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ledgerdesk.imports import InputError, preview
from ledgerdesk.server import create_demo, make_server
from ledgerdesk.store import Store


def encoded(text):
    return base64.b64encode(text.encode()).decode()


MAPPING = {"order_id": "order_id", "amount": "amount", "channel": "channel"}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "test.sqlite3")
        self.batch = self.store.create_batch("synthetic workflow")

    def add(self, side, rows, **kwargs):
        header = "order_id,amount,channel" if side == "orders" else "order_id,transaction_id,amount,event_type,channel"
        data = encoded(header + "\n" + rows + "\n")
        return self.store.import_file(self.batch, side, side + ".csv", data, preview(side, data)["mapping"], **kwargs)

    def test_changed_alias_requires_explicit_replacement_and_preserves_raw_channel(self):
        old = self.add("orders", "A,1,微信", channel_aliases={"微信": "wechat"})
        with self.assertRaises(InputError):
            self.add("orders", "A,1,微信", channel_aliases={"微信": "wx"})
        new = self.add("orders", "A,1,微信", channel_aliases={"微信": "wx"},
                       replace_id=old["id"], reason="correct alias")
        self.assertNotEqual(old["id"], new["id"])
        with self.store.connect() as con:
            row = con.execute("SELECT channel,source_channel FROM entries WHERE import_id=?", (new["id"],)).fetchone()
            self.assertEqual(tuple(row), ("wx", "微信"))

    def test_alias_collisions_after_trimming_are_rejected(self):
        with self.assertRaises(InputError):
            self.store.normalize_aliases({" 微信": "wx", "微信 ": "other"})

    def test_template_mapping_must_be_complete_and_distinct(self):
        for mapping in ({}, dict(MAPPING, amount=""), dict(MAPPING, amount="order_id"),
                        dict(MAPPING, extra="ignored"), dict(MAPPING, amount=["amount"])):
            with self.subTest(mapping=mapping), self.assertRaises(InputError):
                self.store.save_template("bad", "orders", mapping)
        self.assertEqual(self.store.list_templates(), [])

    def test_template_update_versions_copy_and_portable_bundle(self):
        first = self.store.save_template("synthetic", "orders", MAPPING, {"微信": "wechat"})
        second = self.store.save_template("synthetic", "orders", dict(MAPPING, amount="total"), {})
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["revision"], first["revision"] + 1)
        clone = self.store.copy_template(first["id"], "copy")
        self.assertNotEqual(clone["id"], first["id"])
        bundle = self.store.export_templates()
        other = Store(Path(self.temp.name) / "other.sqlite3")
        self.assertEqual(other.import_templates(bundle)["imported"], 2)
        self.assertEqual(len(other.list_templates()), 2)
        self.assertEqual(json.loads(other.list_templates()[0]["mapping"]), dict(MAPPING, amount="total"))
        self.assertNotIn("id", bundle["templates"][0])

    def test_template_bundle_invalid_or_duplicate_rolls_back(self):
        self.store.save_template("keep", "orders", MAPPING)
        bundle = {"format": "ledgerdesk.mapping-templates", "version": 1, "templates": [
            {"name": "new", "side": "orders", "mapping": MAPPING, "channel_aliases": {}},
            {"name": "bad", "side": "orders", "mapping": {}, "channel_aliases": {}}]}
        with self.assertRaises(InputError):
            self.store.import_templates(bundle)
        self.assertEqual([r["name"] for r in self.store.list_templates()], ["keep"])

    def test_history_review_snapshot_does_not_read_future_review(self):
        self.add("orders", "A,2,x")
        self.add("payments", "A,P1,1,sale,x")
        first = self.store.reconcile(self.batch)["run_id"]
        row = self.store.detail(self.batch)["results"][0]
        self.store.review(self.batch, row["case_key"], row["evidence_sha256"], "resolved", "checked later")
        historical = self.store.run_detail(self.batch, first)
        self.assertEqual(historical["results"][0]["review_status"], "pending")
        self.assertEqual(historical["results"][0]["note"], "")
        self.add("orders", "B,1,x")
        second = self.store.reconcile(self.batch)["run_id"]
        comparison = self.store.compare_runs(self.batch, first, second)
        change = next(row for row in comparison["changed"] if row["after"]["order_id"] == "A")
        self.assertEqual(change["changed_fields"], ["review_snapshot"])

    def test_compare_requires_both_runs_in_this_batch(self):
        batch = create_demo(self.store)
        run = self.store.detail(batch)["run"]["id"]
        for before, after in (("missing", run), (run, "missing"), (run, run)):
            if before == after:
                self.assertEqual(self.store.compare_runs(batch, before, after)["counts"]["changed"], 0)
            else:
                with self.assertRaises(InputError):
                    self.store.compare_runs(batch, before, after)
        with self.assertRaises(InputError):
            self.store.compare_runs(self.batch, run, run)

    def test_history_reports_added_removed_amount_reason_and_evidence_changes(self):
        a = self.add("orders", "A,2,x\nB,1,x")
        self.add("payments", "A,P1,1,sale,x")
        first = self.store.reconcile(self.batch)["run_id"]
        self.add("orders", "A,1,x\nC,1,x", replace_id=a["id"], reason="synthetic correction")
        second = self.store.reconcile(self.batch)["run_id"]
        comparison = self.store.compare_runs(self.batch, first, second)
        self.assertEqual(comparison["counts"], {"added": 1, "removed": 1, "changed": 1})
        change = comparison["changed"][0]
        self.assertEqual(change["before"]["expected"], "2.00")
        self.assertEqual(change["after"]["reasons"], ["matched"])
        historical = self.store.run_detail(self.batch, first)
        self.assertEqual(len(historical["results"]), 2)
        self.assertTrue(historical["read_only"])

    def test_archive_tags_preserve_results_and_can_be_restored(self):
        batch = create_demo(self.store)
        before = self.store.detail(batch)["run"]
        self.store.update_batch(batch, tags=["十月", "十月", " 自测 "], archived=True)
        detail = self.store.detail(batch)
        self.assertEqual(detail["batch"]["tags"], ["十月", "自测"])
        self.assertEqual(detail["batch"]["archived"], 1)
        self.assertEqual(detail["run"], before)
        with self.assertRaises(InputError):
            self.store.reconcile(batch)
        self.store.update_batch(batch, tags=[], archived=False)
        self.assertTrue(self.store.reconcile(batch)["reused"])

    def test_v4_upgrade_keeps_all_original_values_and_rolls_back_on_failure(self):
        path = Path(self.temp.name) / "v4.sqlite3"
        with closing(sqlite3.connect(path)) as con:
            con.executescript((Path(__file__).parent / "fixtures/schema_v4.sql").read_text(encoding="utf-8"))
            con.execute("INSERT INTO batches VALUES('old','legacy','keep',0,'2026-10-18',0)")
            con.commit()
        migrate = Store._migrate
        def broken(store, con, version):
            migrate(store, con, version)
            raise sqlite3.OperationalError("failure after migration DDL")
        with patch.object(Store, "_migrate", broken), self.assertRaises(sqlite3.OperationalError):
            Store(path)
        with closing(sqlite3.connect(path)) as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 4)
            self.assertNotIn("archived", [r[1] for r in con.execute("PRAGMA table_info(batches)")])
        upgraded = Store(path)
        self.assertEqual(upgraded.detail("old")["batch"]["description"], "keep")
        with upgraded.connect() as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 6)
            self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])


class HttpWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = make_server(Path(self.temp.name) / "http.sqlite3", 0)
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

    def request(self, path, payload=None):
        headers = {"Content-Type": "application/json", "X-LedgerDesk-Token": getattr(self, "token", "")}
        request = Request(self.url + path, None if payload is None else json.dumps(payload).encode(), headers)
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            data = json.loads(raw) if response.headers.get("Content-Type", "").startswith("application/json") else raw
            return response.status, data

    def test_export_matches_top_filter_search_reason_and_status(self):
        path = f"/api/batches/{self.batch}/export"
        for query, expected in (("group=issues&status=outstanding&q=O1003", ["O1003"]),
                                ("group=matched&status=all", ["O1002", "O1001"]),
                                ("group=all&reason=duplicate_transaction", ["O1006"]),
                                ("group=issues&status=not_required", [])):
            with self.subTest(query=query):
                status, data = self.request(path + "?" + query)
                self.assertEqual(status, 200)
                rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
                self.assertEqual(sorted(row[2] for row in rows[1:]), sorted(expected))

    def test_export_bound_to_displayed_run_and_rejects_bad_filters(self):
        status, data = self.request(f"/api/batches/{self.batch}/export?run_id=outdated")
        self.assertEqual(status, 400)
        self.assertEqual(data["code"], "stale_result")
        for query in ("status=invalid", "reason=invalid", "group=invalid"):
            self.assertEqual(self.request(f"/api/batches/{self.batch}/export?{query}")[0], 400)

    def test_bad_template_has_stable_error_code_and_no_write(self):
        status, result = self.request("/api/templates", {"name": "bad", "side": "orders", "mapping": {}})
        self.assertEqual(status, 400)
        self.assertEqual(result["code"], "invalid_mapping")
        self.assertIn("errors", result)
        self.assertEqual(self.request("/api/templates")[1]["templates"], [])

    def test_portable_templates_and_batch_archival_over_http(self):
        status, original = self.request("/api/templates", {"name": "first", "side": "orders", "mapping": MAPPING})
        self.assertEqual(status, 200)
        status, copy = self.request("/api/templates/copy", {"id": original["id"], "name": "copy"})
        self.assertEqual(status, 200)
        self.assertNotEqual(copy["id"], original["id"])
        status, bundle = self.request("/api/templates/export")
        self.assertEqual(status, 200)
        self.assertEqual(len(bundle["templates"]), 2)
        bundle["templates"] = [dict(bundle["templates"][0], name="imported")]
        self.assertEqual(self.request("/api/templates/import", {"bundle": bundle}), (200, {"imported": 1}))
        self.assertEqual(self.request("/api/templates/delete", {"id": copy["id"]})[0], 200)
        status, updated = self.request(f"/api/batches/{self.batch}/update", {"tags": ["test"], "archived": True})
        self.assertEqual(status, 200)
        self.assertEqual(updated["tags"], ["test"])
        status, error = self.request(f"/api/batches/{self.batch}/reconcile", {})
        self.assertEqual((status, error["code"]), (400, "batch_archived"))
        detail = self.request(f"/api/batches/{self.batch}")[1]
        status, run = self.request(f"/api/batches/{self.batch}/runs/{detail['run']['id']}")
        self.assertEqual(status, 200)
        self.assertTrue(run["read_only"])
