"""Handwritten expectations exercise rules, SQL aggregates and report tasks together."""
import csv
import io
import json
from pathlib import Path
from ledgerdesk.application.rules import RuleService
from ledgerdesk.application.statistics import StatisticsService
from ledgerdesk.application.reporting import ReportingService
from ledgerdesk.application.jobs import JobService
from ledgerdesk.runtime.worker import JobWorker
from tests.support.workspace import WorkspaceTest


class GoldenWorkflowTests(WorkspaceTest):
    def scenarios(self):
        for directory in sorted((Path(__file__).parent / "golden").iterdir()):
            if not directory.is_dir():
                continue
            expected = json.loads((directory / "expected.json").read_text())
            batch = self.store.create_batch("synthetic " + directory.name, is_sample=True)
            for side in ("orders", "payments"):
                self.add(side, (directory / (side + ".csv")).read_text(), batch=batch)
            if expected["tolerance"]:
                service = RuleService(self.store)
                rule = service.create(directory.name, expected["tolerance"])
                service.select(batch, rule["id"])
            self.store.reconcile(batch)
            yield directory.name, batch, expected

    def test_rules_and_sql_totals_match_independent_expected_values(self):
        for name, batch, expected in self.scenarios():
            with self.subTest(name=name):
                data = StatisticsService(self.store).batch(batch)
                for key in ("expected", "actual", "groups", "matched", "issues"):
                    self.assertEqual(data["totals"][key], expected[key])
                self.assertEqual([r["reasons"] for r in self.store.result_page(batch)["items"]], expected["reasons"])

    def test_complete_report_row_counts_for_every_fixture(self):
        for name, batch, expected in self.scenarios():
            with self.subTest(name=name):
                report = b"".join(ReportingService(self.store).stream(batch)).decode("utf-8-sig")
                self.assertEqual(len(list(csv.reader(io.StringIO(report)))), expected["groups"] + 1)

    def test_durable_reports_use_the_same_synthetic_scenarios(self):
        service = JobService(self.store)
        jobs = [(name, service.enqueue("report", batch), expected) for name, batch, expected in self.scenarios()]
        worker = JobWorker(self.store); self.assertTrue(worker.acquire()); self.addCleanup(worker.close)
        while worker.run_once():
            pass
        for name, job, expected in jobs:
            with self.subTest(name=name):
                result = service.get(job["id"])
                self.assertEqual(result["state"], "succeeded")
                report = (self.root / "exports" / result["result"]["filename"]).read_text(encoding="utf-8-sig")
                self.assertEqual(len(list(csv.reader(io.StringIO(report)))), expected["groups"] + 1)
