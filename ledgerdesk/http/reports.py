"""Streaming reports and immutable report profile revisions."""
from .response import Response
from .parameters import single
from ..application.reporting import ReportingService
from ..domain.filters import ResultFilter
from ..domain.report_profiles import COLUMNS
import base64
import json


def get(context, parts, query):
    service = ReportingService(context.store)
    if parts == ["api", "report-profiles"]:
        return Response({"profiles": service.profiles(), "columns": COLUMNS})
    if len(parts) == 4 and parts[:2] == ["api", "batches"] and parts[3] in ("report", "export"):
        format = "csv" if parts[3] == "export" else single(query, "format", "html")
        metadata = {}
        chunks = service.stream(parts[2], ResultFilter.from_query(query), single(query, "run_id"), single(query, "profile_id"), format, metadata)
        mime = "text/csv; charset=utf-8" if format == "csv" else "text/html; charset=utf-8"
        headers = {"Content-Disposition": 'attachment; filename="ledgerdesk-reconciliation.csv"'} if format == "csv" else {}
        def annotated():
            try:
                for chunk in chunks:
                    if "X-LedgerDesk-Run" not in headers:
                        headers["X-LedgerDesk-Run"] = metadata["run_id"]
                        headers["X-LedgerDesk-Report"] = base64.urlsafe_b64encode(json.dumps(metadata, ensure_ascii=False).encode()).decode()
                    yield chunk
            finally:
                chunks.close()
        return Response(annotated(), content_type=mime, headers=headers, stream=True)


def post(context, parts, payload):
    if parts == ["api", "report-profiles"]:
        return Response(ReportingService(context.store).create_profile(payload.get("name"), payload.get("columns")))
