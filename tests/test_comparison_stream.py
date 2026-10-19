"""Bounded comparisons retain counts and last-page semantics."""
from unittest.mock import patch
from ledgerdesk.domain.filters import ResultFilter
from ledgerdesk.persistence.runs import RunRepository
from tests.support.workspace import WorkspaceTest


class ComparisonStreamTests(WorkspaceTest):
    def test_large_difference_page_avoids_whole_payload_loader(self):
        self.pair(count=90)
        old = self.run
        original = self.store.overview(self.batch)["imports"][0]
        self.add("orders", "order_id,amount,channel\n" + "\n".join(f"A{i:04},1,x" for i in range(90)), replace_id=original["id"], reason="synthetic correction")
        new = self.store.reconcile(self.batch)["run_id"]
        expected = self.store.compare_runs(self.batch, old, new)["counts"]
        with patch.object(RunRepository, "payloads", side_effect=AssertionError("no bulk reads")):
            data = self.store.compare_page(self.batch, old, new, page=999, page_size=25)
        self.assertEqual(data["counts"], expected)
        self.assertEqual((data["page"], len(data["items"])), (4, 15))

    def test_same_run_has_no_difference(self):
        self.pair(count=1)
        self.assertEqual(self.store.compare_page(self.batch, self.run, self.run)["total"], 0)
