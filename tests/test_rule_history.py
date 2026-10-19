"""Default compatibility and changed policy review generations."""
from ledgerdesk.application.rules import RuleService
from tests.support.workspace import WorkspaceTest


class RuleHistoryTests(WorkspaceTest):
    def test_default_reuses_run_and_rule_change_preserves_history(self):
        row = self.pair(count=1)[0]
        before = self.store.run_detail(self.batch, self.run)
        self.store.review(self.batch, row["case_key"], row["evidence_sha256"], "resolved", "synthetic original")
        self.assertTrue(self.store.reconcile(self.batch)["reused"])
        rule = RuleService(self.store).create("explicit exact", 0)
        RuleService(self.store).select(self.batch, rule["id"])
        newer = self.store.reconcile(self.batch)["run_id"]
        self.assertNotEqual(self.run, newer)
        self.assertEqual(self.store.run_detail(self.batch, self.run), before)
        self.assertEqual(self.store.result_page(self.batch)["items"][0]["review_status"], "pending")
        self.assertEqual(self.store.compare_page(self.batch, self.run, newer)["counts"]["changed"], 1)

    def test_tolerance_never_hides_duplicate_order(self):
        self.pair("1.00", "2.00", 1)
        self.add("orders", "order_id,amount,channel\nA0000,1.00,x\n")
        service = RuleService(self.store); rule = service.create("wide", 1000000); service.select(self.batch, rule["id"])
        self.store.reconcile(self.batch)
        self.assertEqual(self.store.result_page(self.batch)["items"][0]["reasons"], ["duplicate_order"])
