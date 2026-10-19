"""Merge compact summaries in SQL and retain only the requested difference page."""
import json
from ..domain.comparisons import classify
from .result_queries import ResultQueryRepository
from .runs import RunRepository


class ComparisonRepository:
    @staticmethod
    def page(con, batch_id, older_id, newer_id, page=1, page_size=50):
        ResultQueryRepository.validate_page(page, page_size)
        RunRepository.get(con, batch_id, older_id)
        RunRepository.get(con, batch_id, newer_id)
        cursor = con.execute("""SELECT * FROM (
          SELECT a.case_key,a.summary AS before,b.summary AS after FROM result_lookup a
          LEFT JOIN result_lookup b ON b.run_id=? AND b.case_key=a.case_key WHERE a.run_id=?
          UNION ALL SELECT b.case_key,NULL,b.summary FROM result_lookup b
          LEFT JOIN result_lookup a ON a.run_id=? AND a.case_key=b.case_key
          WHERE b.run_id=? AND a.case_key IS NULL) ORDER BY case_key""", (newer_id, older_id, older_id, newer_id))
        counts, selected, tail, total = {"added": 0, "removed": 0, "changed": 0}, [], [], 0
        offset = (page - 1) * page_size
        for row in cursor:
            item = classify(json.loads(row["before"]) if row["before"] else None, json.loads(row["after"]) if row["after"] else None)
            if item is None:
                continue
            if total % page_size == 0:
                tail = []
            tail.append(item)
            if offset <= total < offset + page_size:
                selected.append(item)
            counts[item["kind"]] += 1
            total += 1
        pages = max(1, (total + page_size - 1) // page_size)
        return {"older_id": older_id, "newer_id": newer_id, "counts": counts, "total": total,
                "page": min(page, pages), "page_size": page_size, "total_pages": pages,
                "items": tail if page > pages else selected}
