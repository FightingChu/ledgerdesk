"""A slow export keeps one live-review snapshot until its generator closes."""
from ledgerdesk.application.reporting import ReportingService
from ledgerdesk.domain.errors import InputError
from tests.support.workspace import WorkspaceTest


class ReportSnapshotTests(WorkspaceTest):
    def test_review_change_after_header_does_not_mix_report_versions(self):
        row = self.pair(count=1)[0]
        stream = ReportingService(self.store).stream(self.batch)
        next(stream)
        self.store.review(self.batch, row["case_key"], row["evidence_sha256"], "resolved", "after header")
        old = b"".join(stream).decode()
        self.assertNotIn("after header", old)
        self.assertIn("after header", b"".join(ReportingService(self.store).stream(self.batch)).decode("utf-8-sig"))

    def test_stale_run_and_invalid_profile_fail_before_first_chunk(self):
        self.pair(count=1)
        with self.assertRaises(InputError):
            next(ReportingService(self.store).stream(self.batch, profile_id="missing"))
        self.add("orders", "order_id,amount,channel\nNEW,1,x\n")
        with self.assertRaises(InputError):
            next(ReportingService(self.store).stream(self.batch))

    def test_closing_a_partial_export_releases_its_snapshot(self):
        self.pair(count=1)
        stream = ReportingService(self.store).stream(self.batch)
        next(stream); stream.close()
        with self.store.connect() as con:
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
