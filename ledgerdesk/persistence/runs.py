"""Run loading, source identity and result writes within caller transactions."""
import json
from ..domain.errors import InputError
from ..domain.reconciliation import RECONCILIATION_VERSION
from ..domain.values import digest
from ..domain.result_summary import lookup_values


class RunRepository:
    @staticmethod
    def fingerprint(con, batch_id):
        batch = con.execute("SELECT input_revision FROM batches WHERE id=?", (batch_id,)).fetchone()
        if batch is None:
            raise InputError("批次不存在", code="not_found")
        files = con.execute("SELECT id,file_sha256,mapping,channel_aliases FROM imports WHERE batch_id=? AND is_active=1 ORDER BY id", (batch_id,))
        return digest({"engine": RECONCILIATION_VERSION, "revision": batch["input_revision"],
                       "files": [tuple(row) for row in files]})

    @staticmethod
    def inputs(con, batch_id):
        sides = {row[0] for row in con.execute("SELECT DISTINCT side FROM imports WHERE batch_id=? AND is_active=1", (batch_id,))}
        if sides != {"orders", "payments"}:
            raise InputError("请先分别导入业务单和支付账单")
        return [dict(row) for row in con.execute("""SELECT e.*,i.side,i.filename FROM entries e
            JOIN imports i ON e.import_id=i.id WHERE i.batch_id=? AND i.is_active=1 ORDER BY e.id""", (batch_id,))]

    @staticmethod
    def previous(con, batch_id):
        latest = con.execute("SELECT id FROM runs WHERE batch_id=? ORDER BY rowid DESC LIMIT 1", (batch_id,)).fetchone()
        return {row["case_key"]: json.loads(row["payload"]) for row in con.execute(
            "SELECT case_key,payload FROM results WHERE run_id=?", (latest["id"] if latest else "",))}

    @staticmethod
    def get(con, batch_id, run_id):
        if not isinstance(run_id, str) or not run_id or len(run_id) > 64:
            raise InputError("核对版本不存在", code="not_found")
        row = con.execute("SELECT * FROM runs WHERE id=? AND batch_id=?", (run_id, batch_id)).fetchone()
        if row is None:
            raise InputError("核对版本不存在或不属于此批次", code="not_found")
        return dict(row)

    @staticmethod
    def payloads(con, run_id):
        return [json.loads(row[0]) for row in con.execute("SELECT payload FROM results WHERE run_id=? ORDER BY rowid", (run_id,))]

    @staticmethod
    def save(con, batch_id, run_id, fingerprint, timestamp, summary, results):
        con.execute("INSERT INTO runs VALUES(?,?,?,?,?)", (run_id, batch_id, fingerprint, timestamp, json.dumps(summary)))
        con.executemany("INSERT INTO results VALUES(?,?,?,?)", [(run_id, row["case_key"], row["evidence_sha256"],
                         json.dumps(row, ensure_ascii=False)) for row in results])
        con.executemany("INSERT INTO result_lookup VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (lookup_values(run_id, position, row) for position, row in enumerate(results, 1)))
