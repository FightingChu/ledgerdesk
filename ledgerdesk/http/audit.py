"""Stream a batch's fixed audit view as CSV or JSON."""
from .parameters import single
from .response import Response
from ..application.audit_export import AuditExportService


def get(context, parts, query):
    if len(parts) != 4 or parts[:2] != ["api", "batches"] or parts[3] != "audit-export":
        return None
    output_format = single(query, "format", "csv")
    action = single(query, "action", "all")
    raw_until = single(query, "until_id", None)
    until_id = None if raw_until in (None, "") else int(raw_until)
    chunks = AuditExportService(context.store).stream(parts[2], action, output_format, until_id)
    mime = "text/csv; charset=utf-8" if output_format == "csv" else "application/x-ndjson; charset=utf-8"
    filename = "ledgerdesk-audit.csv" if output_format == "csv" else "ledgerdesk-audit.jsonl"
    return Response(chunks, content_type=mime, headers={"Content-Disposition": f'attachment; filename="{filename}"'}, stream=True)
