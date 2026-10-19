"""SQL filtering and bounded summary reads; source evidence is loaded one case at a time."""
import json
from ..domain.errors import InputError
from ..domain.filters import ResultFilter
from .runs import RunRepository


class ResultQueryRepository:
    @staticmethod
    def validate_page(page, page_size):
        if type(page) is not int or page < 1 or type(page_size) is not int or not 1 <= page_size <= 100:
            raise InputError("页码须为正整数，每页条数须为 1～100 的整数", code="invalid_pagination")

    @staticmethod
    def resolve(con, batch_id, run_id, historical=False):
        if con.execute("SELECT 1 FROM batches WHERE id=?", (batch_id,)).fetchone() is None:
            raise InputError("批次不存在", code="not_found")
        latest = con.execute("SELECT * FROM runs WHERE batch_id=? ORDER BY rowid DESC LIMIT 1", (batch_id,)).fetchone()
        if run_id is None:
            if historical:
                raise InputError("历史查询须指定核对版本", code="not_found")
            return dict(latest) if latest else None
        run = RunRepository.get(con, batch_id, run_id)
        if not historical and (latest is None or latest["id"] != run_id):
            raise InputError("核对版本已变化，请刷新后查询", code="stale_result")
        return run

    @staticmethod
    def selection(batch_id, run_id, filters, historical=False):
        if not isinstance(filters, ResultFilter):
            raise InputError("筛选条件无效", code="invalid_filter")
        if historical:
            join, args = "", [run_id]
            status, note = "COALESCE(i.snapshot_status,'unknown')", "i.snapshot_note"
            revision = "NULL"
        else:
            join = " LEFT JOIN reviews v ON v.batch_id=? AND v.case_key=i.case_key AND v.evidence_sha256=i.evidence_sha256"
            args = [batch_id, run_id]
            status, note = "COALESCE(v.status,'pending')", "COALESCE(v.note,'')"
            revision = "COALESCE(v.revision,0)"
        where = ["i.run_id=?"]
        if filters.group != "all":
            where.append("i.matched=?")
            args.append(int(filters.group == "matched"))
        if filters.reason != "all":
            where.append("instr(i.reason_tokens,?)>0")
            args.append("|" + filters.reason + "|")
        if filters.status == "not_required":
            where.append("i.matched=1")
        elif filters.status != "all":
            where.append("i.matched=0")
            if filters.status == "outstanding":
                where.append(status + " IN ('pending','in_progress')")
            else:
                where.append(status + "=?")
                args.append(filters.status)
        if filters.q.strip():
            where.append("instr(i.search_text,?)>0")
            args.append(filters.q.strip().lower())
        return {"from": " FROM result_lookup i" + join + " WHERE " + " AND ".join(where),
                "args": args, "columns": "i.summary," + status + " AS review_status," + note + " AS note," + revision + " AS review_revision"}

    @staticmethod
    def count(con, selection):
        return con.execute("SELECT COUNT(*)" + selection["from"], selection["args"]).fetchone()[0]

    @staticmethod
    def summaries(con, selection, limit=None, offset=0):
        sql = "SELECT " + selection["columns"] + selection["from"] + " ORDER BY i.position"
        args = list(selection["args"])
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            args += [limit, offset]
        for row in con.execute(sql, args):
            item = json.loads(row["summary"])
            item.update(review_status=row["review_status"], note=row["note"], review_revision=row["review_revision"])
            yield item

    @staticmethod
    def case(con, batch_id, run, case_key, historical=False):
        if not isinstance(case_key, str) or not case_key or len(case_key) > 128:
            raise InputError("订单核查记录不存在", code="not_found")
        row = con.execute("SELECT payload FROM results WHERE run_id=? AND case_key=?", (run["id"], case_key)).fetchone()
        if row is None:
            raise InputError("订单核查记录不存在", code="not_found")
        item = json.loads(row["payload"])
        if historical:
            snapshot = item.get("review_snapshot")
            item.update(review_status=snapshot["status"] if snapshot else "unknown", note=snapshot["note"] if snapshot else "", review_revision=None)
        else:
            review = con.execute("SELECT status,note,revision FROM reviews WHERE batch_id=? AND case_key=? AND evidence_sha256=?",
                                 (batch_id, case_key, item["evidence_sha256"])).fetchone()
            item.update(review_status=review["status"] if review else "pending", note=review["note"] if review else "", review_revision=review["revision"] if review else 0)
        return item
