"""Audit exports preserve a fixed event bound and stream both formats."""
import csv
import io
import json
from ledgerdesk.application.audit_export import AuditExportService
from ledgerdesk.domain.errors import InputError
from tests.support.workspace import WorkspaceTest


class AuditExportTests(WorkspaceTest):
    def test_csv_and_json_exports_include_all_events_until_anchor(self):
        self.pair(count=2)
        anchor = self.store.audit_page(self.batch)["until_id"]
        self.store.update_batch(self.batch, tags=["after-anchor"])
        csv_data = b"".join(AuditExportService(self.store).stream(self.batch, until_id=anchor))
        rows = list(csv.reader(io.StringIO(csv_data.decode("utf-8-sig"))))
        self.assertEqual(len(rows), anchor + 1)
        json_data = b"".join(AuditExportService(self.store).stream(self.batch, "all", "json", anchor))
        events = [json.loads(line) for line in json_data.decode().splitlines()]
        self.assertEqual(len(events), anchor)
        self.assertTrue(all(event["until_id"] == anchor for event in events))

    def test_action_filter_and_bad_options_are_rejected(self):
        self.pair(count=1)
        data = b"".join(AuditExportService(self.store).stream(self.batch, "reconcile", "json"))
        self.assertTrue(all(json.loads(line)["action"] == "reconcile" for line in data.decode().splitlines()))
        for action, output_format, until in (("bad", "csv", None), ("all", "xml", None), ("all", "csv", -1)):
            with self.subTest(action=action), self.assertRaises(InputError):
                list(AuditExportService(self.store).stream(self.batch, action, output_format, until))
