"""Import lifecycle SQL; parsing, backup and transaction ownership stay in application."""
import json
from ..domain.errors import InputError
from ..domain.values import now


class ImportRepository:
    @staticmethod
    def active(con, batch_id, import_id, side=None):
        row = con.execute("SELECT * FROM imports WHERE id=? AND batch_id=? AND is_active=1", (import_id, batch_id)).fetchone()
        if row is None or (side is not None and row["side"] != side):
            raise InputError("文件不存在、已撤销或不属于当前批次和数据侧，请刷新页面")
        return dict(row)

    @staticmethod
    def previous(con, batch_id, side, file_hash):
        return con.execute("SELECT id,row_count,mapping,channel_aliases FROM imports WHERE batch_id=? AND side=? AND file_sha256=? AND is_active=1",
                           (batch_id, side, file_hash)).fetchone()

    @staticmethod
    def revoke(con, import_id, reason):
        con.execute("UPDATE imports SET is_active=0,revoked_at=?,revoked_reason=? WHERE id=?", (now(), reason, import_id))

    @staticmethod
    def advance(con, batch_id):
        con.execute("UPDATE batches SET input_revision=input_revision+1 WHERE id=?", (batch_id,))

    @staticmethod
    def insert(con, import_id, batch_id, side, filename, file_hash, mapping, records, replace_id, aliases):
        con.execute("""INSERT INTO imports(id,batch_id,side,filename,file_sha256,mapping,row_count,created_at,
            currency_policy,replaces_id,channel_aliases) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (import_id, batch_id, side, filename, file_hash, json.dumps(mapping, ensure_ascii=False),
                     len(records), now(), records[0]["currency_policy"], replace_id,
                     json.dumps(aliases, ensure_ascii=False, sort_keys=True)))
        con.executemany("INSERT INTO entries(import_id,line,channel,order_id,transaction_id,kind,amount_cents,source_channel) VALUES(?,?,?,?,?,?,?,?)",
                        [(import_id, row["line"], row["channel"], row["order_id"], row["transaction_id"],
                          row["kind"], row["amount_cents"], row["source_channel"]) for row in records])
