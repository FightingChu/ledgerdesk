"""Single-order source evidence is bounded independently from result-list pagination."""
from ledgerdesk.application.evidence import EvidenceService
from ledgerdesk.domain.errors import InputError
from unittest.mock import patch
from ledgerdesk.persistence.result_queries import ResultQueryRepository
from tests.support.workspace import WorkspaceTest


class EvidencePageTests(WorkspaceTest):
    def test_diagnostics_reject_missing_materialized_sources(self):
        self.pair(count=1)
        with self.store.connect() as con:
            con.execute("DELETE FROM result_sources WHERE kind='source' AND position=1")
        from ledgerdesk.persistence.diagnostics import inspect_database
        report = inspect_database(self.store.path)
        self.assertFalse(report["source_coverage"])
        self.assertTrue(report["metric_coverage"])
        self.assertEqual(report["status"], "invalid")

    def test_many_source_rows_are_paged_without_legacy_case_loader(self):
        self.add("orders", "order_id,amount,channel\nA,105,x\n")
        self.add("payments", "order_id,transaction_id,amount,event_type,channel\n" + "\n".join(f"A,P{i},1,sale,x" for i in range(105)))
        run = self.store.reconcile(self.batch)["run_id"]
        key = self.store.result_page(self.batch)["items"][0]["case_key"]
        service = EvidenceService(self.store)
        with patch.object(ResultQueryRepository, "case", side_effect=AssertionError("no full JSON")):
            info = service.read(self.batch, key, run)
            self.assertNotIn("rows", info["item"])
            page = service.read(self.batch, key, run, kind="source", page=5, page_size=25)
            self.assertEqual((page["total"], len(page["items"])), (106, 6))

    def test_historical_scope_and_invalid_kind(self):
        row = self.pair(count=1)[0]
        service = EvidenceService(self.store)
        self.assertTrue(service.read(self.batch, row["case_key"], self.run, historical=True)["read_only"])
        with self.assertRaises(InputError):
            service.read(self.batch, row["case_key"], self.run, kind="wrong")
        other = self.store.create_batch("other")
        with self.assertRaises(InputError):
            service.read(other, row["case_key"], self.run)
