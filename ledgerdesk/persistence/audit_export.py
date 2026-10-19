"""Streaming batch audit rows under one fixed event upper bound."""
import json
from ..domain.errors import InputError
from .audit import ACTION_LABELS


class AuditExportRepository:
    @staticmethod
    def rows(con, batch_id, action="all", until_id=None):
        if con.execute("SELECT 1 FROM batches WHERE id=?", (batch_id,)).fetchone() is None:
            raise InputError("批次不存在", code="not_found")
        if action != "all" and action not in ACTION_LABELS:
            raise InputError("未知操作类型", code="invalid_filter")
        if until_id is None:
            until_id = con.execute("SELECT COALESCE(MAX(id),0) FROM audit WHERE batch_id=?", (batch_id,)).fetchone()[0]
        where = " WHERE batch_id=? AND id<=?"
        args = [batch_id, until_id]
        if action != "all":
            where += " AND action=?"
            args.append(action)
        for row in con.execute("SELECT id,action,payload,created_at FROM audit" + where + " ORDER BY id", args):
            value = dict(row)
            value["payload"] = json.loads(value["payload"])
            value["label"] = ACTION_LABELS.get(value["action"], value["action"])
            value["until_id"] = until_id
            yield value
