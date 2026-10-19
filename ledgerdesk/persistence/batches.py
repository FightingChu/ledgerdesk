"""Batch reads and writes; callers own the transaction."""
import json
from ..domain.errors import InputError
from ..domain.values import now


class BatchRepository:
    @staticmethod
    def get(con, batch_id):
        row = con.execute("SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
        if row is None:
            raise InputError("批次不存在", code="not_found")
        batch = dict(row)
        batch["tags"] = json.loads(batch["tags"])
        return batch

    @staticmethod
    def require_editable(con, batch_id):
        batch = BatchRepository.get(con, batch_id)
        if batch["archived"]:
            raise InputError("批次已归档，请先恢复后再操作", code="batch_archived")
        return batch

    @staticmethod
    def create(con, batch_id, name, description, is_sample):
        con.execute("INSERT INTO batches(id,name,description,is_sample,created_at) VALUES(?,?,?,?,?)",
                    (batch_id, name, description, int(is_sample), now()))

    @staticmethod
    def update(con, batch_id, tags, archived):
        con.execute("UPDATE batches SET tags=?,archived=? WHERE id=?",
                    (json.dumps(tags, ensure_ascii=False), int(archived), batch_id))
        return BatchRepository.get(con, batch_id)

    @staticmethod
    def list(con):
        result = [dict(row) for row in con.execute("""
            SELECT b.*, (SELECT COUNT(*) FROM imports i WHERE i.batch_id=b.id AND i.is_active=1) AS file_count,
              (SELECT summary FROM runs r WHERE r.batch_id=b.id ORDER BY rowid DESC LIMIT 1) AS latest_summary,
              (SELECT MAX(created_at) FROM runs r WHERE r.batch_id=b.id) AS last_run
            FROM batches b ORDER BY b.created_at DESC,b.rowid DESC
        """)]
        for batch in result:
            batch["tags"] = json.loads(batch["tags"])
            batch["latest_summary"] = json.loads(batch["latest_summary"]) if batch["latest_summary"] else None
        return result
