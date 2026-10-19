"""Summary and immutable source pages for current or historical cases."""
from .response import Response
from .parameters import paging, single
from ..application.evidence import EvidenceService


def get(context, parts, query):
    if parts[:2] != ["api", "batches"]:
        return None
    historical = len(parts) == 8 and parts[3] == "runs" and parts[5] == "cases"
    current = len(parts) == 6 and parts[3] == "cases"
    if not (historical or current) or parts[-1] not in ("info", "evidence"):
        return None
    key = parts[6] if historical else parts[4]
    run_id = parts[4] if historical else single(query, "run_id")
    page, size = paging(query)
    kind = single(query, "kind", "source") if parts[-1] == "evidence" else None
    return Response(EvidenceService(context.store).read(parts[2], key, run_id, historical, kind, page, size))
