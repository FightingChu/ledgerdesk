"""Workspace pages make per-batch scope explicit without double-counted revenue claims."""
from ledgerdesk.application.statistics import StatisticsService
from ledgerdesk.domain.errors import InputError
from tests.support.workspace import WorkspaceTest


class WorkspaceTests(WorkspaceTest):
    def test_empty_and_archived_batches_are_visible_in_their_own_scope(self):
        service = StatisticsService(self.store)
        data = service.workspace()
        self.assertIsNone(data["items"][0]["summary"])
        self.store.update_batch(self.batch, archived=True)
        self.assertEqual(service.workspace()["total"], 0)
        self.assertEqual(service.workspace(archived=True)["total"], 1)

    def test_paging_stale_flags_and_bad_arguments(self):
        self.pair(count=1)
        self.add("orders", "order_id,amount,channel\nnew,2,x\n")
        self.assertTrue(StatisticsService(self.store).workspace()["items"][0]["stale"])
        with self.assertRaises(InputError):
            StatisticsService(self.store).workspace(page_size=101)
