"""Batch analytics and a workspace overview, without treating duplicated batches as revenue."""
import json
from ..domain.filters import ResultFilter
from ..domain.errors import InputError
from ..persistence.result_queries import ResultQueryRepository
from ..persistence.statistics import StatisticsRepository


class StatisticsService:
    def __init__(self, store):
        self.store = store

    def batch(self, batch_id, filters=None, run_id=None, historical=False, page=1, page_size=25):
        with self.store.connect() as con:
            con.execute("BEGIN")
            run = ResultQueryRepository.resolve(con, batch_id, run_id, historical)
            if run is None:
                raise InputError("请先执行核对", code="not_found")
            selection = StatisticsRepository.selection(batch_id, run["id"], filters or ResultFilter(), historical)
            return {"run_id": run["id"], "historical": historical,
                "stale": not historical and run["input_sha256"] != self.store.source_fingerprint(con, batch_id),
                "totals": StatisticsRepository.totals(con, selection),
                "channels": StatisticsRepository.channels(con, selection, page, page_size),
                "rule_snapshot": json.loads(run["rule_snapshot"]) if run.get("rule_snapshot") else None}

    def workspace(self, page=1, page_size=25, archived=False):
        ResultQueryRepository.validate_page(page, page_size)
        if type(archived) is not bool:
            raise InputError("批次状态无效")
        with self.store.connect() as con:
            con.execute("BEGIN")
            total = con.execute("SELECT COUNT(*) FROM batches WHERE archived=?", (int(archived),)).fetchone()[0]
            pages = max(1, (total + page_size - 1) // page_size)
            page = min(page, pages)
            batches = con.execute("SELECT * FROM batches WHERE archived=? ORDER BY rowid DESC LIMIT ? OFFSET ?",
                                  (int(archived), page_size, (page - 1) * page_size))
            items = []
            for batch in batches:
                run = ResultQueryRepository.resolve(con, batch["id"], None)
                items.append({"batch_id": batch["id"], "name": batch["name"], "is_sample": bool(batch["is_sample"]),
                    "run_id": run["id"] if run else None,
                    "summary": json.loads(run["summary"]) if run else None,
                    "stale": bool(run and run["input_sha256"] != self.store.source_fingerprint(con, batch["id"]))})
            return {"items": items, "page": page, "total": total, "page_size": page_size, "total_pages": pages,
                    "scope": "独立批次最新运行；批次可能包含重复输入，不代表经营收入"}
