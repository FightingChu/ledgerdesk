"""Standalone printable reports escape source text and carry run metadata."""
from ledgerdesk.application.reporting import ReportingService
from tests.support.workspace import WorkspaceTest


class HtmlReportTests(WorkspaceTest):
    def test_user_text_is_escaped_and_print_style_is_embedded(self):
        row = self.pair(count=1)[0]
        self.store.review(self.batch, row["case_key"], row["evidence_sha256"], "resolved", "<script>alert(1)</script>")
        data = b"".join(ReportingService(self.store).stream(self.batch, format="html")).decode()
        self.assertNotIn("<script>", data)
        self.assertIn("&lt;script&gt;", data)
        self.assertIn("<style>", data)
        self.assertIn(self.run, data)
        self.assertIn("</html>", data)

    def test_custom_rule_columns_show_recorded_policy(self):
        self.pair(count=1)
        service = ReportingService(self.store)
        profile = service.create_profile("rule", ["rule", "rule_revision"])
        data = b"".join(service.stream(self.batch, profile_id=profile["id"], format="html")).decode()
        self.assertIn("默认精确核对", data)
