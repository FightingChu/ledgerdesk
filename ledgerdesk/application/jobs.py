"""Validated queue submission, cancellation and explicit retries."""
from ..domain.errors import InputError
from ..domain.jobs.requests import normalize
from ..domain.values import now
from ..persistence.jobs import JobRepository
from ..persistence.reports import ReportProfileRepository
from ..persistence.result_queries import ResultQueryRepository


class JobService:
    def __init__(self, store):
        self.store = store

    def enqueue(self, kind, batch_id=None, payload=None, dedupe_key=None):
        value = normalize(kind, batch_id, {} if payload is None else payload)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if batch_id is not None:
                (self.store.require_editable if kind == "reconcile" else self.store.batch)(con, batch_id)
                value["input_identity"] = self.store.source_fingerprint(con, batch_id)
            if kind == "report":
                run = ResultQueryRepository.resolve(con, batch_id, value["run_id"])
                if run is None or run["input_sha256"] != value["input_identity"]:
                    raise InputError("报告运行已过期", code="stale_result")
                value["run_id"] = run["id"]
                ReportProfileRepository.get(con, value["profile_id"])
            job = JobRepository.enqueue(con, kind, batch_id, value, dedupe_key)
            return job

    def get(self, key):
        with self.store.connect() as con:
            return JobRepository.get(con, key)

    def enqueue_batch(self, batch_ids, request_id):
        if (not isinstance(batch_ids, list) or not 1 <= len(batch_ids) <= 100
                or any(not isinstance(key, str) for key in batch_ids) or len(set(batch_ids)) != len(batch_ids)):
            raise InputError("队列须包含 1～100 个不重复批次", code="invalid_job")
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 64:
            raise InputError("队列请求标识无效", code="invalid_job")
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            prepared = []
            for key in batch_ids:
                self.store.require_editable(con, key)
                prepared.append((key, {"input_identity": self.store.source_fingerprint(con, key)}))
            jobs = [JobRepository.enqueue(con, "reconcile", key, payload, request_id + ":" + key) for key, payload in prepared]
            return {"jobs": jobs, "count": len(jobs)}

    def list(self, page=1, page_size=25, state="all"):
        with self.store.connect() as con:
            con.execute("BEGIN")
            return JobRepository.list(con, page, page_size, state)

    def cancel(self, key):
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            old = JobRepository.get(con, key)
            if old["state"] == "queued":
                return JobRepository.transition(con, key, "cancelled")
            if old["state"] == "running":
                con.execute("UPDATE jobs SET cancel_requested=1,updated_at=? WHERE id=?", (now(), key))
                return JobRepository.get(con, key)
            raise InputError("任务已结束，不能取消", code="job_conflict")

    def retry(self, key):
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            old = JobRepository.get(con, key)
            if old["state"] not in ("failed", "cancelled", "interrupted"):
                raise InputError("只能重试失败、取消或中断的任务", code="job_conflict")
            if old["batch_id"] is not None:
                (self.store.require_editable if old["kind"] == "reconcile" else self.store.batch)(con, old["batch_id"])
                if old["payload"]["input_identity"] != self.store.source_fingerprint(con, old["batch_id"]):
                    raise InputError("批次输入已变化，请提交新任务", code="stale_result")
            JobRepository.transition(con, key, "queued")
            con.execute("UPDATE jobs SET attempt=attempt+1,progress=0,total=1,cancel_requested=0,result=NULL,error='' WHERE id=?", (key,))
            return JobRepository.get(con, key)
