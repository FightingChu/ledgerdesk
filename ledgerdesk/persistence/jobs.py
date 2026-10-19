"""Serialized job claims, durable progress and compare-state lifecycle updates."""
import json
from ..domain.jobs.states import require_transition, STATES
from ..domain.errors import InputError
from ..domain.values import identifier, now
from .result_queries import ResultQueryRepository


def decoded(row):
    value = dict(row)
    value["payload"] = json.loads(value["payload"])
    value["result"] = json.loads(value["result"]) if value["result"] else None
    return value


class JobRepository:
    @staticmethod
    def get(con, key):
        if not isinstance(key, str):
            raise InputError("任务标识无效", code="not_found")
        row = con.execute("SELECT * FROM jobs WHERE id=?", (key,)).fetchone()
        if row is None:
            raise InputError("任务不存在", code="not_found")
        return decoded(row)

    @staticmethod
    def enqueue(con, kind, batch_id, payload, dedupe_key=None):
        if dedupe_key is not None:
            if not isinstance(dedupe_key, str) or not 1 <= len(dedupe_key) <= 128:
                raise InputError("任务请求标识无效", code="invalid_job")
            old = con.execute("SELECT * FROM jobs WHERE dedupe_key=?", (dedupe_key,)).fetchone()
            if old:
                value = decoded(old)
                if (value["kind"], value["batch_id"], value["payload"]) != (kind, batch_id, payload):
                    raise InputError("此请求标识已用于其他任务", code="job_conflict")
                return value
        key, timestamp = identifier(), now()
        con.execute("""INSERT INTO jobs(id,kind,batch_id,payload,dedupe_key,state,attempt,progress,total,phase,
            cancel_requested,created_at,updated_at,result,error) VALUES(?,?,?,?,?,'queued',1,0,1,'等待执行',0,?,?,NULL,'')""",
                    (key, kind, batch_id, json.dumps(payload, ensure_ascii=False), dedupe_key, timestamp, timestamp))
        return JobRepository.get(con, key)

    @staticmethod
    def claim(con):
        row = con.execute("SELECT id FROM jobs WHERE state='queued' ORDER BY rowid LIMIT 1").fetchone()
        if row is None:
            return None
        con.execute("UPDATE jobs SET state='running',phase='开始执行',updated_at=? WHERE id=? AND state='queued'", (now(), row[0]))
        return JobRepository.get(con, row[0])

    @staticmethod
    def transition(con, key, state, result=None, error=""):
        old = JobRepository.get(con, key)
        require_transition(old["state"], state)
        con.execute("UPDATE jobs SET state=?,result=?,error=?,phase=?,updated_at=?,progress=? WHERE id=?",
                    (state, json.dumps(result, ensure_ascii=False) if result is not None else None, error[:1000], {"queued":"等待执行","running":"执行中","succeeded":"已完成","failed":"执行失败","cancelled":"已取消","interrupted":"已中断"}[state], now(),
                     old["total"] if state == "succeeded" else old["progress"], key))
        return JobRepository.get(con, key)

    @staticmethod
    def list(con, page=1, page_size=25, state="all"):
        ResultQueryRepository.validate_page(page, page_size)
        if state not in ("all", *STATES):
            raise InputError("任务筛选无效", code="invalid_filter")
        where, args = ("", []) if state == "all" else (" WHERE state=?", [state])
        total = con.execute("SELECT COUNT(*) FROM jobs" + where, args).fetchone()[0]
        pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, pages)
        rows = con.execute("SELECT * FROM jobs" + where + " ORDER BY rowid DESC LIMIT ? OFFSET ?", [*args, page_size, (page - 1) * page_size])
        return {"items": [decoded(row) for row in rows], "page": page, "page_size": page_size, "total": total, "total_pages": pages}
