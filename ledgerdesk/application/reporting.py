"""Validate before the first chunk and keep reviews in one SQLite read snapshot."""
from dataclasses import asdict
from ..domain.filters import ResultFilter
from ..domain.errors import InputError
from ..domain.values import now
from .. import __version__
from ..persistence.result_queries import ResultQueryRepository
from ..persistence.reports import ReportProfileRepository
from ..reporting.csv_stream import csv_chunks
from ..reporting.html_stream import html_chunks


class ReportingService:
    def __init__(self, store):
        self.store = store

    def profiles(self):
        with self.store.connect() as con:
            return ReportProfileRepository.list(con)

    def create_profile(self, name, columns):
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            return ReportProfileRepository.create(con, name, columns)

    def stream(self, batch_id, filters=None, run_id=None, profile_id=None, format="csv", metadata=None):
        if format not in ("csv", "html"):
            raise InputError("报告格式无效", code="invalid_report")
        filters = filters or ResultFilter()
        with self.store.connect() as con:
            con.execute("BEGIN")
            batch = self.store.batch(con, batch_id)
            run = ResultQueryRepository.resolve(con, batch_id, None)
            if run_id is not None and (run is None or run["id"] != run_id):
                raise InputError("显示的核对版本已变化，请刷新后导出", code="stale_result")
            if run is None or run["input_sha256"] != self.store.source_fingerprint(con, batch_id):
                raise InputError("数据或运行已变化，请重新核对后导出", code="stale_result")
            profile = ReportProfileRepository.get(con, profile_id)
            selection = ResultQueryRepository.selection(batch_id, run["id"], filters)
            rows = ResultQueryRepository.summaries(con, selection)
            context = {"batch": batch, "run": run, "profile": profile, "filters": asdict(filters)}
            if metadata is not None:
                import json
                metadata.update(format="ledgerdesk.report-manifest", version=1, application_version=__version__,
                    batch_id=batch_id, run_id=run["id"], profile_id=profile["id"], profile_revision=profile["revision"],
                    columns=profile["columns"], filters=asdict(filters), requested_at=now(),
                    rule_snapshot=json.loads(run["rule_snapshot"]) if run.get("rule_snapshot") else None,
                    review_scope="one committed read snapshot")
            yield from (csv_chunks if format == "csv" else html_chunks)(rows, context, profile["columns"])
