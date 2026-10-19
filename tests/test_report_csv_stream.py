"""Complete CSV output across chunks, including formula-safe user text."""
import csv
import io
from ledgerdesk.application.reporting import ReportingService
from tests.support.workspace import WorkspaceTest


class CsvStreamTests(WorkspaceTest):
    def test_chunks_include_all_rows_and_only_one_bom(self):
        self.pair(count=205)
        chunks = list(ReportingService(self.store).stream(self.batch))
        self.assertGreater(len(chunks), 2)
        data = b"".join(chunks)
        self.assertEqual(data.count(b"\xef\xbb\xbf"), 1)
        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 206)
        self.assertEqual(rows[-1][2], "A0204")

    def test_custom_column_order_and_formula_escaping(self):
        row = self.pair(count=1)[0]
        self.store.review(self.batch, row["case_key"], row["evidence_sha256"], "resolved", '=HYPERLINK("x")')
        service = ReportingService(self.store)
        profile = service.create_profile("compact", ["note", "difference", "order_id"])
        data = b"".join(service.stream(self.batch, profile_id=profile["id"]))
        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
        self.assertEqual(rows[0], ["处理备注", "差额(元)", "订单号"])
        self.assertTrue(rows[1][0].startswith("'="))
        self.assertEqual(rows[1][1], "-1.00")
