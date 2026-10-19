"""Evidence-scoped review reads and monotonic integer revisions."""
import json
from ..domain.values import now


class ReviewRepository:
    @staticmethod
    def get(con, batch_id, case_key, evidence):
        row = con.execute("SELECT status,note,revision,updated_at FROM reviews WHERE batch_id=? AND case_key=? AND evidence_sha256=?",
                          (batch_id, case_key, evidence)).fetchone()
        return dict(row) if row else {"status": "pending", "note": "", "revision": 0, "updated_at": None}

    @staticmethod
    def result(con, run_id, case_key):
        row = con.execute("SELECT summary FROM result_lookup WHERE run_id=? AND case_key=?", (run_id, case_key)).fetchone()
        return json.loads(row["summary"]) if row else None

    @staticmethod
    def save(con, batch_id, case_key, evidence, status, note):
        con.execute("""INSERT INTO reviews(batch_id,case_key,evidence_sha256,status,note,updated_at,revision)
            VALUES(?,?,?,?,?,?,1) ON CONFLICT(batch_id,case_key,evidence_sha256) DO UPDATE SET
            status=excluded.status,note=excluded.note,updated_at=excluded.updated_at,revision=reviews.revision+1""",
                    (batch_id, case_key, evidence, status, note, now()))
        return ReviewRepository.get(con, batch_id, case_key, evidence)
