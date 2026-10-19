"""Run a reconciliation atomically while keeping business rules SQL-free."""
from ..domain.reconciliation import build_reconciliation
from ..domain.values import identifier, now
from ..persistence.runs import RunRepository
from ..persistence.rules import RuleRepository


class ReconciliationService:
    def __init__(self, store):
        self.store = store

    def run(self, batch_id, expected_identity=None):
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self.store.require_editable(con, batch_id)
            if expected_identity is not None and RunRepository.fingerprint(con, batch_id) != expected_identity:
                from ..domain.errors import InputError
                raise InputError("排队期间输入已变化，请提交新任务", code="stale_result")
            rows = RunRepository.inputs(con, batch_id)
            fingerprint = RunRepository.fingerprint(con, batch_id)
            old = con.execute("SELECT id FROM runs WHERE batch_id=? AND input_sha256=?", (batch_id, fingerprint)).fetchone()
            if old:
                return {"run_id": old["id"], "reused": True}
            run_id = identifier()
            results, summary = build_reconciliation(rows, RunRepository.previous(con, batch_id), run_id, RuleRepository.selected(con, batch_id))
            # These are snapshots at the time of this run, not live review state.
            for row in results:
                review = con.execute("SELECT status,note FROM reviews WHERE batch_id=? AND case_key=? AND evidence_sha256=?",
                                     (batch_id, row["case_key"], row["evidence_sha256"])).fetchone()
                row["review_snapshot"] = {"status": review["status"] if review else "pending",
                                          "note": review["note"] if review else ""}
            RunRepository.save(con, batch_id, run_id, fingerprint, now(), summary, results)
            self.store.audit(con, batch_id, "reconcile", {"run_id": run_id, "summary": summary})
            return {"run_id": run_id, "reused": False}
