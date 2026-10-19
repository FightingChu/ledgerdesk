"""Audit paging, scope, action filters and stable pages while writes arrive."""
from pathlib import Path
import tempfile
import unittest
from ledgerdesk.domain.errors import InputError
from ledgerdesk.store import Store


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "audit.sqlite3")
        self.batch = self.store.create_batch("synthetic audit")
        for i in range(57):
            self.store.update_batch(self.batch, tags=[str(i)])

    def test_pages_are_bounded_ordered_and_payloads_are_objects(self):
        events = []
        for page, count in ((1, 25), (2, 25), (3, 8)):
            result = self.store.audit_page(self.batch, page=page)
            self.assertEqual(result["total"], 58)
            self.assertEqual(len(result["items"]), count)
            self.assertTrue(all(isinstance(r["payload"], dict) for r in result["items"]))
            events += [r["id"] for r in result["items"]]
        self.assertEqual(events, sorted(set(events), reverse=True))
        self.assertEqual(self.store.audit_page(self.batch, page=999)["page"], 3)

    def test_anchor_prevents_duplicates_and_shifts_when_new_events_arrive(self):
        first = self.store.audit_page(self.batch, page_size=10)
        for i in range(12):
            self.store.update_batch(self.batch, tags=["new", str(i)])
        second = self.store.audit_page(self.batch, page=2, page_size=10, until_id=first["until_id"])
        self.assertEqual(second["total"], first["total"])
        self.assertLess(second["items"][0]["id"], first["items"][-1]["id"])
        self.assertEqual(self.store.audit_page(self.batch)["total"], 70)

    def test_filter_scope_archive_and_empty_range(self):
        other = self.store.create_batch("other batch")
        self.store.update_batch(self.batch, archived=True)
        created = self.store.audit_page(self.batch, action="create_batch")
        self.assertEqual(created["total"], 1)
        self.assertNotEqual(created["items"][0]["id"], self.store.audit_page(other)["items"][0]["id"])
        self.assertEqual(self.store.audit_page(self.batch, action="bulk_review")["items"], [])
        self.assertEqual(self.store.audit_page(self.batch, until_id=0)["total"], 0)
        with self.assertRaises(InputError):
            self.store.audit_page("missing")

    def test_bad_filters_pagination_and_anchor_are_rejected(self):
        for options in ({"action": "bad"}, {"action": []}, {"page": 0}, {"page_size": 101},
                        {"page": True}, {"until_id": -1}, {"until_id": True}, {"until_id": "1"}, {"until_id": 2**63}):
            with self.subTest(options=options), self.assertRaises(InputError):
                self.store.audit_page(self.batch, **options)
