"""Report configuration revisions are immutable display choices."""
from ledgerdesk.application.reporting import ReportingService
from ledgerdesk.domain.errors import InputError
from tests.support.workspace import WorkspaceTest


class ReportProfileTests(WorkspaceTest):
    def test_column_order_and_named_revision_are_preserved(self):
        service = ReportingService(self.store)
        a = service.create_profile("audit", ["order_id", "note"])
        b = service.create_profile("audit", ["note", "order_id"])
        self.assertEqual((a["revision"], b["revision"]), (1, 2))
        self.assertEqual(next(p for p in service.profiles() if p["id"] == a["id"])["columns"], ["order_id", "note"])

    def test_empty_duplicate_unknown_and_wrong_type_columns_are_rejected(self):
        for columns in ([], ["note", "note"], ["missing"], "note", [None]):
            with self.subTest(columns=columns), self.assertRaises(InputError):
                ReportingService(self.store).create_profile("bad", columns)
