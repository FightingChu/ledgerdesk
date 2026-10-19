"""Bounded result pages, lazy case evidence and complete filtered reports."""
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
from ledgerdesk.domain.errors import InputError
from ledgerdesk.domain.filters import ResultFilter
from ledgerdesk.imports import preview
from ledgerdesk.server import export_csv
from ledgerdesk.store import Store


def add(store, batch, side, text):
    data = base64.b64encode(text.encode()).decode()
    return store.import_file(batch, side, side + ".csv", data, preview(side, data)["mapping"])


class PaginationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "test.sqlite3")
        self.batch = self.store.create_batch("synthetic pages")
        add(self.store, self.batch, "orders", "order_id,amount,channel\n" + "\n".join(f"A{i:04},2.00,微信" for i in range(105)))
        add(self.store, self.batch, "payments", "order_id,transaction_id,amount,event_type,channel\n" + "\n".join(f"A{i:04},P{i},1.00,sale,微信" for i in range(105)))
        self.run = self.store.reconcile(self.batch)["run_id"]

    def test_pages_are_ordered_bounded_and_contain_no_source_arrays(self):
        keys = []
        for page, count in ((1, 50), (2, 50), (3, 5)):
            result = self.store.result_page(self.batch, ResultFilter(), page=page, run_id=self.run)
            self.assertEqual(result["total"], 105)
            self.assertEqual(result["total_pages"], 3)
            self.assertEqual(len(result["items"]), count)
            for row in result["items"]:
                self.assertNotIn("rows", row)
                self.assertNotIn("duplicate_rows", row)
                keys.append(row["case_key"])
        self.assertEqual(len(set(keys)), 105)
        self.assertEqual(self.store.result_page(self.batch, ResultFilter(), page=999999)["page"], 3)
        overview = self.store.overview(self.batch)
        self.assertNotIn("results", overview)
        self.assertEqual(overview["run"]["id"], self.run)

    def test_case_details_are_loaded_separately_and_enforce_scope(self):
        row = self.store.result_page(self.batch, ResultFilter(), run_id=self.run)["items"][0]
        detail = self.store.case_detail(self.batch, row["case_key"], run_id=self.run)
        self.assertEqual(len(detail["item"]["rows"]), 2)
        self.assertFalse(detail["read_only"])
        other = self.store.create_batch("another")
        with self.assertRaises(InputError):
            self.store.case_detail(other, row["case_key"], run_id=self.run)
        with self.assertRaises(InputError):
            self.store.case_detail(self.batch, "missing", run_id=self.run)

    def test_filters_use_live_reviews_and_export_all_matching_pages(self):
        rows = self.store.result_page(self.batch, ResultFilter(), run_id=self.run)["items"]
        self.store.review(self.batch, rows[0]["case_key"], rows[0]["evidence_sha256"], "resolved", "synthetic checked")
        remaining = self.store.result_page(self.batch, ResultFilter(status="outstanding"), run_id=self.run)
        self.assertEqual(remaining["total"], 104)
        matched = self.store.result_page(self.batch, ResultFilter(q="微信", status="resolved"), run_id=self.run)
        self.assertEqual(matched["total"], 1)
        literal = self.store.result_page(self.batch, ResultFilter(q="%_"), run_id=self.run)
        self.assertEqual(literal["total"], 0)
        report = export_csv(self.store.overview(self.batch), self.store.export_rows(self.batch, ResultFilter(), self.run))
        self.assertEqual(len(list(csv.reader(io.StringIO(report.decode("utf-8-sig"))))), 106)

    def test_sql_filter_intersections_match_domain_rules(self):
        from ledgerdesk.server import create_demo
        batch = create_demo(self.store)
        detail = self.store.detail(batch)
        issues = [row for row in detail["results"] if row["reasons"] != ["matched"]]
        for row, status in zip(issues, ("resolved", "in_progress")):
            self.store.review(batch, row["case_key"], row["evidence_sha256"], status, "synthetic reviewed")
        detail = self.store.detail(batch)
        for group in ("all", "issues", "matched"):
            for status in ("all", "outstanding", "pending", "in_progress", "resolved", "not_required"):
                for reason in ("all", "matched", "duplicate_transaction"):
                    filters = ResultFilter(group=group, status=status, reason=reason)
                    expected = [row["case_key"] for row in filters.apply(detail["results"])]
                    actual = self.store.result_page(batch, filters)
                    self.assertEqual([row["case_key"] for row in actual["items"]], expected)
                    self.assertEqual(actual["total"], len(expected))

    def test_current_pages_reject_changed_run_but_history_remains_readable(self):
        row = self.store.result_page(self.batch, ResultFilter(), run_id=self.run)["items"][0]
        add(self.store, self.batch, "orders", "order_id,amount,channel\nNEW,1.00,微信\n")
        stale = self.store.result_page(self.batch, ResultFilter(), run_id=self.run)
        self.assertTrue(stale["stale"])
        new = self.store.reconcile(self.batch)["run_id"]
        with self.assertRaises(InputError) as error:
            self.store.result_page(self.batch, ResultFilter(), page=2, run_id=self.run)
        self.assertEqual(error.exception.code, "stale_result")
        history = self.store.result_page(self.batch, ResultFilter(), run_id=self.run, historical=True)
        self.assertTrue(history["read_only"])
        self.assertEqual(history["total"], 105)
        self.assertEqual(self.store.case_detail(self.batch, row["case_key"], run_id=self.run, historical=True)["run_id"], self.run)
        self.assertEqual(self.store.result_page(self.batch, ResultFilter(), run_id=new)["total"], 106)

    def test_bad_pagination_is_rejected_and_empty_batches_are_supported(self):
        for page, size in ((0, 50), (-1, 50), (True, 50), (1, 0), (1, 101), (1, "50")):
            with self.subTest(page=page, size=size), self.assertRaises(InputError):
                self.store.result_page(self.batch, ResultFilter(), page=page, page_size=size)
        empty = self.store.create_batch("empty")
        self.assertEqual(self.store.result_page(empty, ResultFilter())["items"], [])

    def test_diagnostics_identify_missing_summary_index_rows(self):
        from ledgerdesk.persistence.diagnostics import inspect_database
        with self.store.connect() as con:
            con.execute("DELETE FROM result_lookup WHERE position=1")
        report = inspect_database(self.store.path)
        self.assertEqual(report["integrity"], "ok")
        self.assertFalse(report["index_coverage"])
        self.assertEqual(report["status"], "invalid")

    def test_page_count_and_rows_share_one_read_snapshot(self):
        from ledgerdesk.persistence.result_queries import ResultQueryRepository
        first = self.store.result_page(self.batch)["items"][0]
        original = ResultQueryRepository.count
        def review_after_count(con, selection):
            total = original(con, selection)
            self.store.review(self.batch, first["case_key"], first["evidence_sha256"], "resolved", "changed during query")
            return total
        with patch.object(ResultQueryRepository, "count", side_effect=review_after_count):
            result = self.store.result_page(self.batch, ResultFilter(status="outstanding"), page_size=1)
        self.assertEqual((result["total"], len(result["items"])), (105, 1))
        self.assertEqual(result["items"][0]["review_status"], "pending")
        self.assertEqual(self.store.result_page(self.batch, ResultFilter(status="outstanding"))["total"], 104)

    def test_comparison_pages_never_include_source_arrays(self):
        original = self.run
        file = self.store.overview(self.batch)["imports"][0]
        text = "order_id,amount,channel\n" + "\n".join(f"A{i:04},1.00,微信" for i in range(105))
        data = base64.b64encode(text.encode()).decode()
        self.store.import_file(self.batch, "orders", "corrected.csv", data, preview("orders", data)["mapping"],
                               replace_id=file["id"], reason="correct synthetic amounts")
        newer = self.store.reconcile(self.batch)["run_id"]
        page = self.store.compare_page(self.batch, original, newer, page=2)
        self.assertEqual(page["counts"]["changed"], 105)
        self.assertEqual(len(page["items"]), 50)
        self.assertNotIn('"rows"', json.dumps(page))

    def test_v5_backfill_preserves_payloads_and_live_review_and_failure_rolls_back(self):
        # Copy a real synthetic run into a v5 schema, without the new lookup table.
        path = Path(self.temp.name) / "old.sqlite3"
        tables = ("batches", "imports", "entries", "runs", "results", "reviews", "audit", "mapping_templates")
        row = self.store.result_page(self.batch)["items"][0]
        self.store.review(self.batch, row["case_key"], row["evidence_sha256"], "resolved", "retained")
        with self.store.connect() as source, closing(sqlite3.connect(path)) as target:
            target.executescript((Path(__file__).parent / "fixtures/schema_v5.sql").read_text(encoding="utf-8"))
            for table in tables:
                rows = source.execute("SELECT * FROM " + table + " ORDER BY rowid").fetchall()
                if rows:
                    target.executemany("INSERT INTO " + table + " VALUES(" + ",".join("?" for _ in rows[0]) + ")", [tuple(r) for r in rows])
            target.commit()
        migrate = Store._migrate
        def broken(store, con, version):
            migrate(store, con, version)
            raise sqlite3.OperationalError("failure after backfill")
        with patch.object(Store, "_migrate", broken), self.assertRaises(sqlite3.OperationalError):
            Store(path)
        with closing(sqlite3.connect(path)) as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 5)
            self.assertIsNone(con.execute("SELECT name FROM sqlite_master WHERE name='result_lookup'").fetchone())
        upgraded = Store(path)
        page = upgraded.result_page(self.batch, ResultFilter(status="resolved"), run_id=self.run)
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["items"][0]["note"], "retained")
        with self.store.connect() as before, upgraded.connect() as after:
            for table in tables:
                self.assertEqual([tuple(r) for r in before.execute("SELECT * FROM " + table + " ORDER BY rowid")],
                                 [tuple(r) for r in after.execute("SELECT * FROM " + table + " ORDER BY rowid")])
            self.assertEqual(after.execute("SELECT COUNT(*) FROM result_lookup").fetchone()[0], 105)
            self.assertEqual(after.execute("PRAGMA foreign_key_check").fetchall(), [])


class LargeBatchTests(unittest.TestCase):
    def test_five_thousand_groups_use_bounded_summary_query_and_lazy_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "large.sqlite3")
            batch = store.create_batch("synthetic 5001 groups")
            add(store, batch, "orders", "order_id,amount,channel\n" + "\n".join(f"L{i:05},2,x" for i in range(5001)))
            add(store, batch, "payments", "order_id,transaction_id,amount,event_type,channel\n" + "\n".join(f"L{i:05},P{i},1,sale,x" for i in range(5001)))
            run = store.reconcile(batch)["run_id"]
            with patch.object(Store, "detail", side_effect=AssertionError("bulk detail must not be used")):
                overview = store.overview(batch)
                page = store.result_page(batch, ResultFilter(), run_id=run)
                self.assertEqual(page["total"], 5001)
                self.assertEqual(len(page["items"]), 50)
                self.assertNotIn("results", overview)
                self.assertLess(len(json.dumps(page)), 100000)
                case = store.case_detail(batch, page["items"][0]["case_key"], run_id=run)
                self.assertEqual(len(case["item"]["rows"]), 2)


class HttpPaginationTests(unittest.TestCase):
    def setUp(self):
        from ledgerdesk.server import make_server
        self.temp = tempfile.TemporaryDirectory()
        path = Path(self.temp.name) / "http.sqlite3"
        self.store = Store(path)
        self.batch = self.store.create_batch("synthetic HTTP pages")
        add(self.store, self.batch, "orders", "order_id,amount,channel\n" + "\n".join(f"A{i:04},2,微信" for i in range(105)))
        add(self.store, self.batch, "payments", "order_id,transaction_id,amount,event_type,channel\n" + "\n".join(f"A{i:04},P{i},1,sale,微信" for i in range(105)))
        self.run = self.store.reconcile(self.batch)["run_id"]
        self.server = make_server(path, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, suffix):
        try:
            response = urlopen(Request(self.url + f"/api/batches/{self.batch}/" + suffix), timeout=20)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            return response.status, json.loads(raw) if response.headers.get("Content-Type", "").startswith("application/json") else raw

    def test_overview_page_and_case_skip_legacy_bulk_loader(self):
        with patch.object(Store, "detail", side_effect=AssertionError("bulk loader must not run")):
            status, overview = self.request("overview")
            self.assertEqual(status, 200)
            self.assertNotIn("results", overview)
            status, page = self.request("results?page=2&page_size=25&run_id=" + self.run)
            self.assertEqual(status, 200)
            self.assertEqual((page["page"], len(page["items"]), page["total"]), (2, 25, 105))
            self.assertNotIn("rows", page["items"][0])
            status, detail = self.request("cases/" + page["items"][0]["case_key"] + "?run_id=" + self.run)
            self.assertEqual(status, 200)
            self.assertEqual(len(detail["item"]["rows"]), 2)
            status, report = self.request("export?run_id=" + self.run + "&page_size=1")
            self.assertEqual(status, 200)
            report_rows = list(csv.reader(io.StringIO(report.decode("utf-8-sig"))))
            self.assertEqual(len(report_rows), 106)

    def test_invalid_parameters_and_blank_batch_do_not_return_server_errors(self):
        for query in ("page=0", "page=-1", "page=abc", "page=1&page=2", "page_size=101", "page_size=0", "page_size=2.5", "run_id=", "status=bad"):
            with self.subTest(query=query):
                self.assertEqual(self.request("results?" + query)[0], 400)
        self.batch = self.store.create_batch("empty")
        status, empty = self.request("results")
        self.assertEqual(status, 200)
        self.assertEqual(empty["items"], [])

    def test_old_page_refused_after_rerun_but_historical_page_and_case_are_available(self):
        old = self.run
        key = self.store.result_page(self.batch)["items"][0]["case_key"]
        add(self.store, self.batch, "orders", "order_id,amount,channel\nNEW,1,微信\n")
        new = self.store.reconcile(self.batch)["run_id"]
        status, error = self.request("results?page=2&run_id=" + old)
        self.assertEqual((status, error["code"]), (400, "stale_result"))
        status, page = self.request("runs/" + old + "/results?page=2")
        self.assertEqual(status, 200)
        self.assertTrue(page["read_only"])
        self.assertEqual(self.request("runs/" + old + "/cases/" + key)[0], 200)
        status, differences = self.request("compare-page?from=" + old + "&to=" + new + "&page_size=1")
        self.assertEqual(status, 200)
        self.assertEqual(differences["counts"]["added"], 1)
        self.assertEqual(len(differences["items"]), 1)
