"""Batch-scoped audit pages with a fixed upper event id across page turns."""
import json
from ..domain.errors import InputError
from ..domain.values import now
from .result_queries import ResultQueryRepository

ACTION_LABELS = {"select_rule": "选择核查规则", "create_batch": "创建批次", "update_batch": "更新批次设置", "import_file": "导入文件",
                 "revoke_import": "撤销文件", "replace_import": "替换文件", "reconcile": "执行核对",
                 "review": "更新处理记录", "bulk_review": "批量处理差异"}


class AuditRepository:
    @staticmethod
    def append(con, batch_id, action, payload):
        con.execute("INSERT INTO audit(batch_id,action,payload,created_at) VALUES(?,?,?,?)",
                    (batch_id, action, json.dumps(payload, ensure_ascii=False), now()))

    @staticmethod
    def page(store, batch_id, page=1, page_size=25, action="all", until_id=None):
        ResultQueryRepository.validate_page(page, page_size)
        if not isinstance(action, str) or action not in {"all", *ACTION_LABELS}:
            raise InputError("未知操作类型", code="invalid_filter")
        if until_id is not None and (type(until_id) is not int or not 0 <= until_id < 2**63):
            raise InputError("操作记录范围无效", code="invalid_pagination")
        with store.connect() as con:
            con.execute("BEGIN")
            store.batch(con, batch_id)
            if until_id is None:
                until_id = con.execute("SELECT COALESCE(MAX(id),0) FROM audit WHERE batch_id=?", (batch_id,)).fetchone()[0]
            where, args = " WHERE batch_id=? AND id<=?", [batch_id, until_id]
            if action != "all":
                where += " AND action=?"
                args.append(action)
            total = con.execute("SELECT COUNT(*) FROM audit" + where, args).fetchone()[0]
            pages = max(1, (total + page_size - 1) // page_size)
            page = min(page, pages)
            items = [dict(row) for row in con.execute("SELECT id,action,payload,created_at FROM audit" + where +
                     " ORDER BY id DESC LIMIT ? OFFSET ?", [*args, page_size, (page - 1) * page_size])]
            for item in items:
                item["payload"] = json.loads(item["payload"])
            return {"items": items, "page": page, "page_size": page_size, "total": total,
                    "total_pages": pages, "until_id": until_id, "actions": ACTION_LABELS}
