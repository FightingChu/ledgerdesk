"""Filtered SQL aggregates in the same snapshot as their associated run."""
from .result_queries import ResultQueryRepository
from ..domain.metrics import format_totals
from ..domain.reconciliation import LABELS

METRICS = ",".join(f"COALESCE(SUM(m.{name}),0) AS {name}" for name in ("expected", "actual", "difference", "sales", "refunds"))


class StatisticsRepository:
    @staticmethod
    def selection(batch_id, run_id, filters, historical=False):
        value = ResultQueryRepository.selection(batch_id, run_id, filters, historical)
        value["from"] = value["from"].replace(" FROM result_lookup i", " FROM result_lookup i JOIN result_metrics m ON m.run_id=i.run_id AND m.case_key=i.case_key", 1)
        return value

    @staticmethod
    def totals(con, selection):
        sql = "SELECT COUNT(*) AS groups,COALESCE(SUM(i.matched),0) AS matched," + METRICS + selection["from"]
        result = format_totals(con.execute(sql, selection["args"]).fetchone())
        result["issues"] = result["groups"] - result["matched"]
        result["reasons"] = {name: con.execute("SELECT COUNT(*)" + selection["from"] + " AND instr(i.reason_tokens,?)>0",
            [*selection["args"], "|" + name + "|"]).fetchone()[0] for name in LABELS}
        return result

    @staticmethod
    def channels(con, selection, page, page_size):
        ResultQueryRepository.validate_page(page, page_size)
        total = con.execute("SELECT COUNT(DISTINCT m.channel)" + selection["from"], selection["args"]).fetchone()[0]
        pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, pages)
        sql = "SELECT m.channel,COUNT(*) AS groups,SUM(i.matched) AS matched," + METRICS + selection["from"]
        rows = con.execute(sql + " GROUP BY m.channel ORDER BY m.channel LIMIT ? OFFSET ?",
                           [*selection["args"], page_size, (page - 1) * page_size])
        items = [format_totals(row) for row in rows]
        for row in items:
            row["issues"] = row["groups"] - row["matched"]
        return {"items": items, "total": total, "page": page, "page_size": page_size, "total_pages": pages}
