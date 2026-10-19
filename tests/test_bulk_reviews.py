"""Synthetic review races, atomic rollback, retries and unchanged historical evidence."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from ledgerdesk.domain.errors import InputError
from ledgerdesk.domain.filters import ResultFilter
from ledgerdesk.persistence.reviews import ReviewRepository
from ledgerdesk.server import create_demo
from ledgerdesk.store import Store


class BulkReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "reviews.sqlite3")
        self.batch = create_demo(self.store)
        self.run = self.store.overview(self.batch)["run"]["id"]
        self.rows = self.store.result_page(self.batch, ResultFilter(group="issues"))["items"]
        self.items = [{"case_key": r["case_key"], "evidence_sha256": r["evidence_sha256"],
                       "expected_revision": r["review_revision"]} for r in self.rows[:2]]

    def save(self, items=None, **kwargs):
        return self.store.bulk_review(self.batch, self.run, self.items if items is None else items,
                                      kwargs.get("status", "resolved"), kwargs.get("note", "synthetic checked"))

    def state(self):
        with self.store.connect() as con:
            return ([tuple(r) for r in con.execute("SELECT * FROM reviews ORDER BY rowid")],
                    [tuple(r) for r in con.execute("SELECT * FROM audit ORDER BY id")])

    def test_bulk_updates_revision_audit_and_live_filter_without_rewriting_history(self):
        history = self.store.run_detail(self.batch, self.run)
        result = self.save()
        self.assertEqual(result["count"], 2)
        self.assertTrue(all(r["review_revision"] == 1 for r in result["items"]))
        live = self.store.result_page(self.batch, ResultFilter(status="resolved"))
        self.assertEqual(live["total"], 2)
        self.assertEqual(self.store.run_detail(self.batch, self.run), history)
        detail = self.store.case_detail(self.batch, self.items[0]["case_key"], run_id=self.run)["item"]
        self.assertEqual((detail["note"], detail["review_revision"]), ("synthetic checked", 1))
        events = self.store.audit_page(self.batch, action="review")["items"]
        self.assertEqual(len(events), 2)
        for event in events:
            self.assertEqual(event["payload"]["before"]["revision"], 0)
            self.assertEqual(event["payload"]["after"]["revision"], 1)
            self.assertEqual(event["payload"]["operation_id"], result["operation_id"])
        self.assertEqual(self.store.audit_page(self.batch, action="bulk_review")["items"][0]["payload"]["count"], 2)

    def test_last_item_conflict_rolls_back_first_item_and_all_audit(self):
        second = self.items[1]
        self.store.review(self.batch, second["case_key"], second["evidence_sha256"], "in_progress", "other page",
                          run_id=self.run, expected_revision=0)
        before = self.state()
        with self.assertRaises(InputError) as error:
            self.save()
        self.assertEqual(error.exception.code, "review_conflict")
        self.assertEqual(self.state(), before)

    def test_repeated_request_does_not_duplicate_audit_or_updates(self):
        self.save()
        before = self.state()
        with self.assertRaises(InputError) as error:
            self.save()
        self.assertEqual(error.exception.code, "review_conflict")
        self.assertEqual(self.state(), before)

    def test_two_concurrent_pages_only_one_can_commit(self):
        barrier = threading.Barrier(2)
        def submit(note):
            barrier.wait(timeout=10)
            try:
                self.save(note=note)
                return "saved"
            except InputError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, ("first page", "second page")))
        self.assertCountEqual(results, ["saved", "review_conflict"])
        self.assertEqual(self.store.audit_page(self.batch, action="bulk_review")["total"], 1)
        notes = {r["note"] for r in self.store.result_page(self.batch, ResultFilter(status="resolved"))["items"]}
        self.assertEqual(len(notes), 1)

    def test_single_review_detects_conflict_even_with_same_timestamp(self):
        item = self.items[0]
        with patch("ledgerdesk.persistence.reviews.now", return_value="2026-10-19T00:00:00+00:00"):
            self.store.review(self.batch, item["case_key"], item["evidence_sha256"], "in_progress", "first",
                              run_id=self.run, expected_revision=0)
            with self.assertRaises(InputError) as error:
                self.store.review(self.batch, item["case_key"], item["evidence_sha256"], "resolved", "second",
                                  run_id=self.run, expected_revision=0)
            self.assertEqual(error.exception.code, "review_conflict")
            self.store.review(self.batch, item["case_key"], item["evidence_sha256"], "resolved", "second",
                              run_id=self.run, expected_revision=1)
        self.assertEqual(self.store.case_detail(self.batch, item["case_key"])["item"]["review_revision"], 2)

    def test_invalid_selection_status_note_and_revisions_never_write(self):
        cases = [[], self.items * 51, [self.items[0], self.items[0]], [None], "not a list"]
        for value in (None, True, -1, 0.0, "0", 2**53):
            cases.append([dict(self.items[0], expected_revision=value)])
        before = self.state()
        for items in cases:
            with self.subTest(items=items), self.assertRaises(InputError):
                self.save(items=items)
        for status, note in (("resolved", "  "), ("pending", "reason"), ([], "reason"), ("resolved", "x" * 1001), ("resolved", None)):
            with self.subTest(status=status), self.assertRaises(InputError):
                self.save(status=status, note=note)
        self.assertEqual(self.state(), before)

    def test_matching_or_foreign_or_missing_last_case_rejects_whole_batch(self):
        matched = self.store.result_page(self.batch, ResultFilter(group="matched"))["items"][0]
        invalid = [{"case_key": matched["case_key"], "evidence_sha256": matched["evidence_sha256"], "expected_revision": 0},
                   dict(self.items[1], case_key="missing"), dict(self.items[1], evidence_sha256="wrong")]
        other = create_demo(self.store)
        foreign = self.store.result_page(other, ResultFilter(group="issues"))["items"][0]
        # Same business key in another batch still has distinct evidence.
        invalid.append({"case_key": foreign["case_key"], "evidence_sha256": foreign["evidence_sha256"], "expected_revision": 0})
        before = self.state()
        for last in invalid:
            with self.subTest(last=last), self.assertRaises(InputError):
                self.save(items=[self.items[0], last])
            self.assertEqual(self.state(), before)

    def test_archived_and_changed_inputs_or_runs_reject_all_items(self):
        self.store.update_batch(self.batch, archived=True)
        with self.assertRaises(InputError) as error:
            self.save()
        self.assertEqual(error.exception.code, "batch_archived")
        self.store.update_batch(self.batch, archived=False)
        with self.store.connect() as con:
            con.execute("UPDATE batches SET input_revision=input_revision+1 WHERE id=?", (self.batch,))
        before = self.state()
        with self.assertRaises(InputError) as error:
            self.save()
        self.assertEqual(error.exception.code, "stale_result")
        self.assertEqual(self.state(), before)
        self.store.reconcile(self.batch)
        with self.assertRaises(InputError) as error:
            self.save()
        self.assertEqual(error.exception.code, "stale_result")

    def test_database_failure_after_second_write_rolls_back_everything(self):
        save = ReviewRepository.save
        count = 0
        def fail_after_write(*args):
            nonlocal count
            result = save(*args)
            count += 1
            if count == 2:
                raise RuntimeError("synthetic storage failure")
            return result
        before = self.state()
        with patch.object(ReviewRepository, "save", side_effect=fail_after_write), self.assertRaises(RuntimeError):
            self.save()
        self.assertEqual(self.state(), before)

    def test_legacy_python_entry_still_increments_revision(self):
        item = self.items[0]
        self.store.review(self.batch, item["case_key"], item["evidence_sha256"], "in_progress", "legacy")
        detail = self.store.detail(self.batch)
        row = next(r for r in detail["results"] if r["case_key"] == item["case_key"])
        self.assertEqual(row["review_revision"], 1)

    def test_maximum_selection_saves_one_hundred_and_no_more(self):
        from tests.test_pagination import add
        batch = self.store.create_batch("synthetic limit")
        add(self.store, batch, "orders", "order_id,amount,channel\n" + "\n".join(f"{i},1,x" for i in range(100)))
        add(self.store, batch, "payments", "order_id,transaction_id,amount,event_type,channel\n0,P0,2,sale,x\n")
        run = self.store.reconcile(batch)["run_id"]
        rows = self.store.result_page(batch, page_size=100)["items"]
        items = [{"case_key": r["case_key"], "evidence_sha256": r["evidence_sha256"], "expected_revision": 0} for r in rows]
        result = self.store.bulk_review(batch, run, items, "in_progress", "")
        self.assertEqual(result["count"], 100)
        self.assertEqual(self.store.audit_page(batch, action="review")["total"], 100)
