"""Atomic single and bulk review workflows with evidence and revision checks."""
from ..domain.errors import InputError
from ..domain.reviews import validate_review, validate_items, validate_revision
from ..domain.values import identifier, require_text
from ..persistence.result_queries import ResultQueryRepository
from ..persistence.reviews import ReviewRepository


class ReviewService:
    def __init__(self, store):
        self.store = store

    def bulk(self, batch_id, run_id, items, status, note):
        if status not in ("in_progress", "resolved"):
            raise InputError("批量处理仅支持处理中或已处理")
        return self._save(batch_id, require_text(run_id, "核对版本", 64), validate_items(items), status, note, bulk=True)

    def single(self, batch_id, case_key, evidence, status, note, run_id=None, expected_revision=None):
        # Existing Python callers may still omit both concurrency fields.
        if run_id is not None or expected_revision is not None:
            run_id = require_text(run_id, "核对版本", 64)
            validate_revision(expected_revision)
        item = {"case_key": require_text(case_key, "差异标识", 128),
                "evidence_sha256": require_text(evidence, "证据版本", 128), "expected_revision": expected_revision}
        return self._save(batch_id, run_id, [item], status, note, bulk=False)

    def _save(self, batch_id, run_id, items, status, note, bulk):
        note = validate_review(status, note)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self.store.require_editable(con, batch_id)
            run = ResultQueryRepository.resolve(con, batch_id, run_id)
            if not run or run["input_sha256"] != self.store.source_fingerprint(con, batch_id):
                raise InputError("数据有更新，请重新核对后再处理差异", code="stale_result")
            operation_id = identifier() if bulk else None
            saved = []
            for item in items:
                key, evidence = item["case_key"], item["evidence_sha256"]
                result = ReviewRepository.result(con, run["id"], key)
                if not result or evidence != result["evidence_sha256"]:
                    raise InputError("所选差异记录已变化，请刷新结果后重新选择", code="stale_result")
                if result["reasons"] == ["matched"]:
                    raise InputError("金额一致的记录无需人工处理", code="invalid_selection")
                before = ReviewRepository.get(con, batch_id, key, evidence)
                if item["expected_revision"] is not None and before["revision"] != item["expected_revision"]:
                    raise InputError("处理记录已被其他操作修改；本次全部未保存，请刷新后重试", code="review_conflict")
                after = ReviewRepository.save(con, batch_id, key, evidence, status, note)
                self.store.audit(con, batch_id, "review", {"case_key": key, "evidence_sha256": evidence,
                    "order_id": result["order_id"], "channel": result["channel"], "run_id": run["id"],
                    "status": status, "note": note, "before": before, "after": after, "operation_id": operation_id})
                saved.append({"case_key": key, "review_revision": after["revision"]})
            if bulk:
                self.store.audit(con, batch_id, "bulk_review", {"operation_id": operation_id, "run_id": run["id"],
                    "count": len(items), "status": status, "note": note})
            return {"saved": True, "count": len(items), "run_id": run["id"], "items": saved, "operation_id": operation_id}
