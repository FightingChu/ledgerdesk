"""Read summary and source pages without deserializing complete result JSON."""
import json
from ..domain.errors import InputError
from ..domain.evidence import validate_kind
from .result_queries import ResultQueryRepository


class EvidenceRepository:
    @staticmethod
    def info(con, batch_id, run, case_key, historical=False):
        row = con.execute("SELECT summary FROM result_lookup WHERE run_id=? AND case_key=?", (run["id"], case_key)).fetchone()
        if row is None:
            raise InputError("核查记录不存在", code="not_found")
        item = json.loads(row[0])
        if historical:
            review = item.get("review_snapshot") or {"status": "unknown", "note": ""}
            item.update(review_status=review["status"], note=review["note"], review_revision=None)
        else:
            from .reviews import ReviewRepository
            review = ReviewRepository.get(con, batch_id, case_key, item["evidence_sha256"])
            item.update(review_status=review["status"], note=review["note"], review_revision=review["revision"])
        return item

    @staticmethod
    def page(con, run_id, case_key, kind, page, page_size):
        validate_kind(kind)
        ResultQueryRepository.validate_page(page, page_size)
        where, args = " WHERE run_id=? AND case_key=? AND kind=?", (run_id, case_key, kind)
        total = con.execute("SELECT COUNT(*) FROM result_sources" + where, args).fetchone()[0]
        pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, pages)
        rows = con.execute("SELECT payload FROM result_sources" + where + " ORDER BY position LIMIT ? OFFSET ?",
                           (*args, page_size, (page - 1) * page_size))
        return {"items": [json.loads(row[0]) for row in rows], "page": page, "page_size": page_size,
                "total": total, "total_pages": pages, "kind": kind}
