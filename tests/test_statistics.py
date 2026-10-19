"""SQL channel aggregation follows the exact result filter intersection."""
from ledgerdesk.application.statistics import StatisticsService
from ledgerdesk.domain.filters import ResultFilter
from tests.support.workspace import WorkspaceTest


class StatisticsTests(WorkspaceTest):
    def test_totals_and_live_review_filter_match_detail(self):
        rows = self.pair(count=7)
        self.store.review(self.batch, rows[0]["case_key"], rows[0]["evidence_sha256"], "resolved", "checked")
        data = StatisticsService(self.store).batch(self.batch, ResultFilter(status="resolved"))
        self.assertEqual(data["totals"]["groups"], 1)
        self.assertEqual(data["totals"]["expected"], "2.00")
        self.assertEqual(data["totals"]["difference"], "-1.00")
        self.assertEqual(data["channels"]["items"][0]["groups"], 1)

    def test_historical_statistics_use_run_snapshot(self):
        row = self.pair(count=1)[0]
        self.store.review(self.batch, row["case_key"], row["evidence_sha256"], "resolved", "later")
        data = StatisticsService(self.store).batch(self.batch, ResultFilter(status="resolved"), self.run, historical=True)
        self.assertEqual(data["totals"]["groups"], 0)

    def test_channels_are_paged_and_unknown_run_rejected(self):
        self.pair(count=1)
        self.add("orders", "order_id,amount,channel\nB,1,y\nC,2,z\n")
        self.store.reconcile(self.batch)
        data = StatisticsService(self.store).batch(self.batch, page=2, page_size=1)
        self.assertEqual((data["channels"]["total"], len(data["channels"]["items"])), (3, 1))
