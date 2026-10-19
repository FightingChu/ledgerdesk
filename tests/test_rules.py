"""Tolerance never clears duplicate or missing-side exceptions."""
from ledgerdesk.application.rules import RuleService
from ledgerdesk.domain.errors import InputError
from tests.support.workspace import WorkspaceTest


class RuleTests(WorkspaceTest):
    def test_tolerance_is_reviewable_and_preserves_difference(self):
        self.pair("1.01", "1.00", 1)
        rules = RuleService(self.store)
        policy = rules.create("synthetic cents", 1)
        rules.select(self.batch, policy["id"])
        self.assertTrue(self.store.overview(self.batch)["stale"])
        self.store.reconcile(self.batch)
        row = self.store.result_page(self.batch)["items"][0]
        self.assertEqual(row["reasons"], ["within_tolerance"])
        self.assertEqual(row["difference"], "-0.01")
        self.assertEqual(row["review_status"], "pending")
        self.assertEqual(self.store.overview(self.batch)["run"]["summary"]["matched"], 0)

    def test_rule_revisions_are_immutable(self):
        service = RuleService(self.store)
        a, b = service.create("same", 1), service.create("same", 2)
        self.assertEqual((a["revision"], b["revision"]), (1, 2))
        self.assertNotEqual(a["id"], b["id"])
        self.assertEqual(next(p for p in service.list() if p["id"] == a["id"])["tolerance_cents"], 1)

    def test_invalid_tolerances_and_archived_selection_are_rejected(self):
        service = RuleService(self.store)
        for value in (-1, 1000001, True, "1", 0.1):
            with self.subTest(value=value), self.assertRaises(InputError):
                service.create("bad", value)
        policy = service.create("valid", 1)
        self.store.update_batch(self.batch, archived=True)
        with self.assertRaises(InputError):
            service.select(self.batch, policy["id"])
