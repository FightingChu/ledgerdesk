"""Public compatibility facade for application workflows and SQLite repositories."""
import json
from .imports import parse
from .domain.errors import InputError
from .domain.money import money
from .domain.values import now, identifier, digest, require_text
from .domain.reconciliation import LABELS, REVIEW_LABELS, RECONCILIATION_VERSION
from .domain.mappings import normalize_aliases
from .domain.history import compare_results
from .persistence.database import Database
from .persistence.migrations import SCHEMA_VERSION
from .persistence.templates import TemplateRepository
from .persistence.runs import RunRepository
from .application.reconciliation import ReconciliationService


class Store(Database):
    normalize_aliases = staticmethod(normalize_aliases)

    def list_templates(self, side=None):
        return TemplateRepository(self).list(side)

    def save_template(self, name, side, mapping, channel_aliases=None):
        return TemplateRepository(self).save(name, side, mapping, channel_aliases)

    def delete_template(self, template_id):
        return TemplateRepository(self).delete(template_id)

    def copy_template(self, template_id, name):
        return TemplateRepository(self).copy(template_id, name)

    def export_templates(self):
        return TemplateRepository(self).export()

    def import_templates(self, bundle):
        return TemplateRepository(self).import_bundle(bundle)

    @staticmethod
    def source_fingerprint(con, batch_id):
        return RunRepository.fingerprint(con, batch_id)

    def reconcile(self, batch_id):
        return ReconciliationService(self).run(batch_id)

    @staticmethod
    def batch(con, batch_id):
        batch = con.execute("SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
        if batch is None:
            raise InputError("批次不存在")
        batch = dict(batch)
        batch["tags"] = json.loads(batch["tags"])
        return batch

    @classmethod
    def require_editable(cls, con, batch_id):
        batch = cls.batch(con, batch_id)
        if batch["archived"]:
            raise InputError("批次已归档，请先恢复后再操作", code="batch_archived")
        return batch

    def update_batch(self, batch_id, tags=None, archived=None):
        if tags is not None:
            if not isinstance(tags, list) or len(tags) > 20:
                raise InputError("批次最多包含 20 个标签")
            tags = list(dict.fromkeys(require_text(tag, "标签", 30) for tag in tags))
        if archived is not None and type(archived) is not bool:
            raise InputError("归档状态必须是布尔值")
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            original = self.batch(con, batch_id)
            con.execute("UPDATE batches SET tags=?,archived=? WHERE id=?",
                        (json.dumps(original["tags"] if tags is None else tags, ensure_ascii=False),
                         original["archived"] if archived is None else int(archived), batch_id))
            updated = self.batch(con, batch_id)
            self.audit(con, batch_id, "update_batch", {"tags": updated["tags"], "archived": bool(updated["archived"])})
        return updated

    @staticmethod
    def audit(con, batch_id, action, payload):
        con.execute("INSERT INTO audit(batch_id,action,payload,created_at) VALUES(?,?,?,?)",
                    (batch_id, action, json.dumps(payload, ensure_ascii=False), now()))

    def create_batch(self, name, description="", is_sample=False):
        name = require_text(name, "批次名称", 80)
        if not isinstance(description, str) or len(description) > 500:
            raise InputError("批次说明最多 500 字符")
        batch_id = identifier()
        with self.connect() as con:
            con.execute("INSERT INTO batches(id,name,description,is_sample,created_at) VALUES(?,?,?,?,?)",
                        (batch_id, name, description.strip(), int(is_sample), now()))
            self.audit(con, batch_id, "create_batch", {"is_sample": bool(is_sample)})
        return batch_id

    def list_batches(self):
        with self.connect() as con:
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

    @staticmethod
    def active_import(con, batch_id, import_id, side=None):
        row = con.execute("SELECT * FROM imports WHERE id=? AND batch_id=? AND is_active=1",
                          (import_id, batch_id)).fetchone()
        if row is None or (side is not None and row["side"] != side):
            raise InputError("文件不存在、已撤销或不属于当前批次和数据侧，请刷新页面")
        return dict(row)

    def import_backup(self):
        destination = self.path.with_name(self.path.name + f".before-import-{identifier()}.sqlite3")
        self.backup(destination)
        return destination.name

    def revoke_import(self, batch_id, import_id, reason):
        reason = require_text(reason, "撤销原因", 500)
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self.require_editable(con, batch_id)
            original = self.active_import(con, batch_id, import_id)
            backup = self.import_backup()
            con.execute("UPDATE imports SET is_active=0,revoked_at=?,revoked_reason=? WHERE id=?",
                        (now(), reason, import_id))
            con.execute("UPDATE batches SET input_revision=input_revision+1 WHERE id=?", (batch_id,))
            self.audit(con, batch_id, "revoke_import", {"import_id": import_id, "filename": original["filename"],
                       "reason": reason, "backup": backup})
        return {"revoked": True, "import_id": import_id}

    def import_file(self, batch_id, side, filename, content, mapping, replace_id=None, reason="", channel_aliases=None):
        filename = require_text(filename, "文件名", 200)
        file_hash, records = parse(side, content, mapping)
        aliases = self.normalize_aliases(channel_aliases)
        for record in records:
            record["source_channel"] = record["channel"]
            record["channel"] = aliases.get(record["channel"], record["channel"])
        if replace_id is not None:
            replace_id = require_text(replace_id, "被替换文件", 64)
            reason = require_text(reason, "替换原因", 500)
        with self.connect() as con:
            # Serialize check+insert: repeated or concurrent requests cannot add twice.
            con.execute("BEGIN IMMEDIATE")
            self.require_editable(con, batch_id)
            if replace_id:
                original = self.active_import(con, batch_id, replace_id, side)
            previous = con.execute("SELECT id,row_count,mapping,channel_aliases FROM imports WHERE batch_id=? AND side=? AND file_sha256=? AND is_active=1",
                                   (batch_id, side, file_hash)).fetchone()
            if previous:
                if replace_id and previous["id"] != replace_id:
                    raise InputError("替换文件已作为另一份有效文件导入，请先核实文件关系")
                if json.loads(previous["mapping"]) == mapping and json.loads(previous["channel_aliases"]) == aliases:
                    return {"id": previous["id"], "row_count": previous["row_count"], "duplicate": True}
                if not replace_id:
                    raise InputError("同一文件已按其他映射或渠道别名导入；请使用替换文件修正", code="conflict")
            backup = None
            if replace_id:
                backup = self.import_backup()
                con.execute("UPDATE imports SET is_active=0,revoked_at=?,revoked_reason=? WHERE id=?",
                            (now(), reason, replace_id))
            import_id = identifier()
            con.execute("INSERT INTO imports(id,batch_id,side,filename,file_sha256,mapping,row_count,created_at,currency_policy,replaces_id,channel_aliases) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (import_id, batch_id, side, filename, file_hash,
                         json.dumps(mapping, ensure_ascii=False), len(records), now(), records[0]["currency_policy"], replace_id,
                         json.dumps(aliases, ensure_ascii=False, sort_keys=True)))
            con.executemany("INSERT INTO entries(import_id,line,channel,order_id,transaction_id,kind,amount_cents,source_channel) VALUES(?,?,?,?,?,?,?,?)",
                [(import_id, row["line"], row["channel"], row["order_id"], row["transaction_id"],
                  row["kind"], row["amount_cents"], row["source_channel"]) for row in records])
            con.execute("UPDATE batches SET input_revision=input_revision+1 WHERE id=?", (batch_id,))
            self.audit(con, batch_id, "import_file", {"import_id": import_id, "side": side,
                       "filename": filename, "file_sha256": file_hash, "rows": len(records)})
            if replace_id:
                self.audit(con, batch_id, "replace_import", {"import_id": replace_id, "filename": original["filename"],
                           "replacement_id": import_id, "replacement_filename": filename, "reason": reason, "backup": backup})
        return {"id": import_id, "row_count": len(records), "duplicate": False}

    def detail(self, batch_id):
        with self.connect() as con:
            con.execute("BEGIN")
            batch = self.batch(con, batch_id)
            files = [dict(row) for row in con.execute("SELECT id,side,filename,file_sha256,row_count,created_at,currency_policy,is_active,revoked_at,revoked_reason,replaces_id,channel_aliases FROM imports WHERE batch_id=? ORDER BY rowid", (batch_id,))]
            latest = con.execute("SELECT * FROM runs WHERE batch_id=? ORDER BY rowid DESC LIMIT 1", (batch_id,)).fetchone()
            results = []
            if latest:
                for row in con.execute("""
                    SELECT r.payload,v.status,v.note,v.updated_at FROM results r
                    LEFT JOIN reviews v ON v.batch_id=? AND v.case_key=r.case_key AND v.evidence_sha256=r.evidence_sha256
                    WHERE r.run_id=? ORDER BY r.rowid
                """, (batch_id, latest["id"])):
                    item = json.loads(row["payload"])
                    item.update(review_status=row["status"] or "pending", note=row["note"] or "", reviewed_at=row["updated_at"])
                    results.append(item)
            # Compute stale state using the same source fingerprint as reconcile.
            stale = bool(latest and latest["input_sha256"] != self.source_fingerprint(con, batch_id))
            audit = [dict(row) for row in con.execute("SELECT action,payload,created_at FROM audit WHERE batch_id=? ORDER BY id DESC LIMIT 50", (batch_id,))]
            return {"batch": batch, "imports": files, "run": ({"id": latest["id"], "created_at": latest["created_at"],
                    "summary": json.loads(latest["summary"])} if latest else None),
                    "results": results, "stale": stale, "audit": audit}

    def history(self, batch_id, limit=30):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise InputError("历史列表每次最多返回 100 项")
        with self.connect() as con:
            self.batch(con, batch_id)
            history = [dict(row) for row in con.execute(
                "SELECT id,created_at,summary,input_sha256 FROM runs WHERE batch_id=? ORDER BY rowid DESC LIMIT ?",
                (batch_id, limit))]
            for run in history:
                run["summary"] = json.loads(run["summary"])
            return history

    def run_detail(self, batch_id, run_id):
        with self.connect() as con:
            con.execute("BEGIN")
            self.batch(con, batch_id)
            run = RunRepository.get(con, batch_id, run_id)
            run["summary"] = json.loads(run["summary"])
            results = RunRepository.payloads(con, run_id)
            for result in results:
                snapshot = result.get("review_snapshot")
                result["review_status"] = snapshot["status"] if snapshot else "unknown"
                result["note"] = snapshot["note"] if snapshot else ""
            return {"run": run, "results": results, "read_only": True}

    def compare_runs(self, batch_id, older_id, newer_id):
        with self.connect() as con:
            con.execute("BEGIN")
            self.batch(con, batch_id)
            RunRepository.get(con, batch_id, older_id)
            RunRepository.get(con, batch_id, newer_id)
            result = compare_results(RunRepository.payloads(con, older_id), RunRepository.payloads(con, newer_id))
            return {"older_id": older_id, "newer_id": newer_id, **result}

    def review(self, batch_id, case_key, evidence_hash, status, note):
        if not isinstance(status, str) or status not in REVIEW_LABELS:
            raise InputError("未知处理状态")
        if not isinstance(note, str) or len(note) > 1000:
            raise InputError("处理备注最多 1000 字符")
        if status == "resolved" and not note.strip():
            raise InputError("标记已处理时必须填写处理依据")
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self.require_editable(con, batch_id)
            latest = con.execute("SELECT id,input_sha256 FROM runs WHERE batch_id=? ORDER BY rowid DESC LIMIT 1", (batch_id,)).fetchone()
            if not latest or latest["input_sha256"] != self.source_fingerprint(con, batch_id):
                raise InputError("数据有更新，请重新核对后再处理差异")
            result = con.execute("SELECT payload,evidence_sha256 FROM results WHERE run_id=? AND case_key=?", (latest["id"], case_key)).fetchone()
            if not result or evidence_hash != result["evidence_sha256"]:
                raise InputError("差异记录已变化，请刷新页面")
            if json.loads(result["payload"])["reasons"] == ["matched"]:
                raise InputError("金额一致的记录无需人工处理")
            con.execute("INSERT INTO reviews VALUES(?,?,?,?,?,?) ON CONFLICT(batch_id,case_key,evidence_sha256) DO UPDATE SET status=excluded.status,note=excluded.note,updated_at=excluded.updated_at",
                        (batch_id, case_key, evidence_hash, status, note.strip(), now()))
            self.audit(con, batch_id, "review", {"case_key": case_key, "status": status, "note": note.strip()})
