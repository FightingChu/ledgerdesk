import base64
from concurrent.futures import ThreadPoolExecutor
import csv
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ledgerdesk.imports import InputError, cents, money, parse, preview
from ledgerdesk.server import create_demo, export_csv, make_server, safe_cell
from ledgerdesk.store import Store


def content(text, encoding="utf-8-sig"):
    return base64.b64encode(text.encode(encoding)).decode()


def orders(*rows):
    return "order_id,amount,channel\n" + "\n".join(rows) + "\n"


def payments(*rows):
    return "order_id,transaction_id,amount,event_type,channel\n" + "\n".join(rows) + "\n"


class ImportTests(unittest.TestCase):
    def test_exact_cents(self):
        self.assertEqual(cents("0.29"), 29)
        self.assertEqual(cents("001.20"), 120)
        self.assertEqual(money(-123456), "-1,234.56")

    def test_invalid_money_rejected(self):
        for value in ("-1", "1.001", "NaN", "Infinity", "1e3", "1,000.00", "", "10000000000.01"):
            with self.subTest(value=value), self.assertRaises(InputError):
                cents(value)

    def test_gb18030_mapping_and_leading_zeros(self):
        data = content("订单号,预计净到账,渠道\n000012,12.30,微信\n", "gb18030")
        mapping = preview("orders", data)["mapping"]
        _, rows = parse("orders", data, mapping)
        self.assertEqual(rows[0]["order_id"], "000012")
        self.assertEqual(rows[0]["channel"], "微信")
        self.assertEqual(rows[0]["amount_cents"], 1230)

    def test_malformed_columns_and_duplicate_headers(self):
        for text in ("a,a\n1,2\n", "a,b\n1\n", "a,b\n", 'a,b\n"open,2'):
            with self.subTest(text=text), self.assertRaises(InputError):
                preview("orders", content(text))

    def test_mapping_cannot_reuse_columns(self):
        with self.assertRaises(InputError):
            parse("orders", content(orders("A,1,x")), {"order_id":"order_id","amount":"amount","channel":"order_id"})

    def test_other_currency_and_unknown_type_rejected(self):
        for text in (payments("A,P1,1,chargeback,x"),
                     "order_id,transaction_id,amount,event_type,channel,currency\nA,P1,1,sale,x,USD\n"):
            data = content(text)
            with self.assertRaises(InputError):
                parse("payments", data, preview("payments", data)["mapping"])

    def test_blank_rows_ignored_and_zero_valid(self):
        data = content("order_id,amount,channel\n\nA,0,x\n,,\n")
        self.assertEqual(preview("orders", data)["row_count"], 1)

    def test_control_characters_rejected(self):
        data = content(orders("A\tB,1,x"))
        with self.assertRaises(InputError):
            parse("orders", data, preview("orders", data)["mapping"])


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/"ledger.sqlite3"
        self.store = Store(self.path)
        self.batch = self.store.create_batch("测试批次")

    def tearDown(self):
        self.temp.cleanup()

    def add(self, side, text, batch=None, mapping=None):
        encoded = content(text)
        return self.store.import_file(batch or self.batch, side, side+".csv", encoded,
                                      mapping or preview(side, encoded)["mapping"])

    def result(self):
        self.store.reconcile(self.batch)
        return self.store.detail(self.batch)

    def test_refunds_are_subtracted_exactly(self):
        self.add("orders", orders("A,0.29,x"))
        self.add("payments", payments("A,P1,0.30,sale,x", "A,R1,0.01,refund,x"))
        row = self.result()["results"][0]
        self.assertEqual(row["actual"], "0.29")
        self.assertEqual(row["reasons"], ["matched"])

    def test_no_files_or_only_one_side_cannot_run(self):
        with self.assertRaises(InputError):
            self.store.reconcile(self.batch)
        self.add("orders", orders("A,1,x"))
        with self.assertRaises(InputError):
            self.store.reconcile(self.batch)

    def test_invalid_file_is_atomic(self):
        with self.assertRaises(InputError) as error:
            self.add("orders", orders("A,1,x", "B,1.001,x"))
        self.assertEqual(error.exception.errors[0]["line"], 3)
        self.assertEqual(self.store.detail(self.batch)["imports"], [])
        with self.store.connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM entries").fetchone()[0], 0)

    def test_same_file_import_is_idempotent_and_scoped(self):
        first = self.add("orders", orders("A,1,x"))
        again = self.add("orders", orders("A,1,x"))
        self.assertEqual(first["id"], again["id"])
        self.assertTrue(again["duplicate"])
        another = self.store.create_batch("另一个批次")
        self.assertFalse(self.add("orders", orders("A,1,x"), another)["duplicate"])

    def test_concurrent_duplicate_import_only_inserts_once(self):
        def submit(_):
            return self.add("orders", orders("A,1,x"))
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(submit, range(4)))
        self.assertEqual(sum(not row["duplicate"] for row in results), 1)
        self.assertEqual(len(self.store.detail(self.batch)["imports"]), 1)

    def test_same_file_different_mapping_requires_new_batch(self):
        data = content("order_id,amount,channel,alternate\nA,1,x,y\n")
        mapping = preview("orders", data)["mapping"]
        self.store.import_file(self.batch, "orders", "one.csv", data, mapping)
        with self.assertRaises(InputError):
            self.store.import_file(self.batch, "orders", "one.csv", data, dict(mapping,channel="alternate"))

    def test_same_order_id_across_channels_not_merged(self):
        self.add("orders", orders("A,1,x", "A,2,y"))
        self.add("payments", payments("A,P1,1,sale,x", "A,P1,2,sale,y"))
        detail = self.result()
        self.assertEqual(detail["run"]["summary"]["matched"], 2)

    def test_duplicate_orders_block_match_even_when_amounts_equal(self):
        self.add("orders", orders("A,1,x", "A,1,x"))
        self.add("payments", payments("A,P1,2,sale,x"))
        self.assertEqual(self.result()["results"][0]["reasons"], ["duplicate_order"])

    def test_duplicate_transaction_across_orders_flags_both(self):
        self.add("orders", orders("A,1,x", "B,1,x"))
        self.add("payments", payments("A,P1,1,sale,x", "B,P1,1,sale,x"))
        detail = self.result()
        self.assertTrue(all(row["reasons"] == ["duplicate_transaction"] for row in detail["results"]))

    def test_single_sided_zero_records_do_not_match(self):
        self.add("orders", orders("A,0,x"))
        self.add("payments", payments("B,P1,0,sale,x"))
        reasons = {row["order_id"]:row["reasons"] for row in self.result()["results"]}
        self.assertEqual(reasons, {"A":["order_only"],"B":["payment_only"]})

    def test_reconcile_reuses_result_and_persists_after_reopen(self):
        self.add("orders", orders("A,1,x"))
        self.add("payments", payments("A,P1,1,sale,x"))
        first = self.store.reconcile(self.batch)
        second = self.store.reconcile(self.batch)
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertTrue(second["reused"])
        self.assertEqual(Store(self.path).detail(self.batch)["results"][0]["actual"], "1.00")

    def mismatch(self):
        self.add("orders", orders("A,3,x"))
        self.add("payments", payments("A,P1,1,sale,x"))
        return self.result()["results"][0]

    def test_review_requires_note_and_never_hides_difference(self):
        row = self.mismatch()
        with self.assertRaises(InputError):
            self.store.review(self.batch,row["case_key"],row["evidence_sha256"],"resolved","")
        self.store.review(self.batch,row["case_key"],row["evidence_sha256"],"resolved","已与原单核实")
        actual = Store(self.path).detail(self.batch)["results"][0]
        self.assertEqual(actual["review_status"], "resolved")
        self.assertEqual(actual["reasons"], ["amount_mismatch"])
        self.assertEqual(actual["difference"], "-2.00")

    def test_stale_result_cannot_be_reviewed_or_exported(self):
        row = self.mismatch()
        self.add("payments", payments("A,P2,2,sale,x"))
        detail = self.store.detail(self.batch)
        self.assertTrue(detail["stale"])
        with self.assertRaises(InputError):
            export_csv(detail)
        with self.assertRaises(InputError):
            self.store.review(self.batch,row["case_key"],row["evidence_sha256"],"resolved","旧记录")

    def test_changed_evidence_resets_review_unchanged_keeps_it(self):
        self.add("orders", orders("A,3,x", "B,3,x"))
        self.add("payments", payments("A,P1,1,sale,x", "B,P2,1,sale,x"))
        for row in self.result()["results"]:
            self.store.review(self.batch,row["case_key"],row["evidence_sha256"],"resolved","已核实")
        self.add("payments", payments("A,P3,1,sale,x"))
        rows = {row["order_id"]:row for row in self.result()["results"]}
        self.assertEqual(rows["A"]["review_status"], "pending")
        self.assertEqual(rows["B"]["review_status"], "resolved")

    def test_wrong_evidence_hash_rejected(self):
        row = self.mismatch()
        with self.assertRaises(InputError):
            self.store.review(self.batch,row["case_key"],"outdated","resolved","核实")

    def test_export_and_formula_escaping(self):
        row = self.mismatch()
        self.store.review(self.batch,row["case_key"],row["evidence_sha256"],"resolved","=HYPERLINK(1)")
        data = export_csv(self.store.detail(self.batch))
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
        self.assertEqual(rows[1][10], "'=HYPERLINK(1)")
        self.assertEqual(rows[1][5], "-2.00")
        self.assertEqual(safe_cell("  @formula"), "'  @formula")

    def test_sample_is_labeled_and_covers_five_issues(self):
        batch = create_demo(self.store)
        detail = self.store.detail(batch)
        self.assertEqual(detail["batch"]["is_sample"], 1)
        self.assertEqual(detail["run"]["summary"]["issues"], 5)
        self.assertEqual(detail["run"]["summary"]["matched"], 2)
        self.assertIn("合成样例", export_csv(detail).decode("utf-8-sig"))

    def test_backup_restores_and_cannot_overwrite(self):
        self.mismatch()
        backup = Path(self.temp.name)/"backup.sqlite3"
        self.store.backup(backup)
        restored = Store(backup)
        self.assertEqual(restored.detail(self.batch)["run"]["summary"]["issues"], 1)
        with self.assertRaises(InputError):
            self.store.backup(backup)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = make_server(Path(self.temp.name)/"web.sqlite3", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.token = self.request("/api/bootstrap")[1]["token"]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.temp.cleanup()

    def request(self, path, data=None, token=True, headers=None):
        extra = dict(headers or {})
        payload = None
        if data is not None:
            extra["Content-Type"] = "application/json"
            if token:
                extra["X-LedgerDesk-Token"] = self.token
            payload = json.dumps(data).encode()
        req = Request(self.url+path, payload, extra)
        try:
            response = urlopen(req, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            parsed = json.loads(raw) if response.headers.get("Content-Type", "").startswith("application/json") else raw
            return response.status, parsed, response.headers

    def test_browser_assets_and_traversal_rejected(self):
        for path in ("/", "/app.js", "/style.css"):
            status, _, headers = self.request(path)
            self.assertEqual(status, 200)
            self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertEqual(self.request("/../../data/ledgerdesk.sqlite3")[0], 404)

    def test_cross_origin_bad_host_and_missing_token_rejected(self):
        self.assertEqual(self.request("/api/demo", {}, token=False)[0], 403)
        self.assertEqual(self.request("/api/demo", {}, headers={"Origin":"https://external.invalid"})[0], 403)
        self.assertEqual(self.request("/api/bootstrap", headers={"Host":"external.invalid"})[0], 403)

    def test_full_http_sample_review_export(self):
        status, created, _ = self.request("/api/demo", {})
        self.assertEqual(status, 200)
        batch = created["batch_id"]
        status, detail, _ = self.request("/api/batches/"+batch)
        self.assertEqual(status, 200)
        row = next(row for row in detail["results"] if row["order_id"] == "O1003")
        status, _, _ = self.request(f"/api/batches/{batch}/review", {
            "case_key":row["case_key"],"evidence_sha256":row["evidence_sha256"],"status":"resolved","note":"核实渠道少入账 2 元"})
        self.assertEqual(status, 200)
        status, raw, headers = self.request(f"/api/batches/{batch}/export")
        self.assertEqual(status, 200)
        self.assertIn("核实渠道少入账 2 元", raw.decode("utf-8-sig"))
        self.assertIn("attachment", headers["Content-Disposition"])

    def test_invalid_json_type_and_oversize_length(self):
        self.assertEqual(self.request("/api/batches", {"name":""})[0], 400)
        self.assertEqual(self.request("/api/preview", {"side":"orders","content":"invalid"})[0], 400)
        status, _, _ = self.request("/api/demo", {}, headers={"Content-Length":str(9*1024*1024)})
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
