"""SQLite persistence and deterministic reconciliation rules."""
from collections import Counter, defaultdict
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

from .imports import InputError, money, parse

SCHEMA_VERSION = 4
RECONCILIATION_VERSION = 3

LABELS = {"matched": "金额一致", "amount_mismatch": "金额不一致", "order_only": "仅业务单",
          "payment_only": "仅支付账单", "duplicate_order": "重复业务单", "duplicate_transaction": "重复流水"}
REVIEW_LABELS = {"pending": "待处理", "in_progress": "处理中", "resolved": "已处理"}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def identifier():
    return uuid.uuid4().hex


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def require_text(value, label, maximum):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise InputError(f"{label}须为 1～{maximum} 个字符")
    return value.strip()


class Store:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Inspect existing files read-only before changing schema or journal settings.
        if self.path.exists():
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as con:
                self._check_version(con)
        with self.connect() as con:
            # v2 -> v3 rebuilds the parent imports table. Disable FK enforcement
            # before BEGIN, then validate all references before the transaction commits.
            con.execute("PRAGMA foreign_keys=OFF")
            con.execute("BEGIN IMMEDIATE")
            version = self._check_version(con)
            if version == 0:
                self._create_v1(con)
            elif version < SCHEMA_VERSION:
                self.backup(self.path.with_name(
                    self.path.name + f".pre-v{version}-to-v{SCHEMA_VERSION}-{identifier()}.sqlite3"))
            for previous in range(version or 1, SCHEMA_VERSION):
                self._migrate(con, previous)
            if con.execute("PRAGMA foreign_key_check").fetchone():
                raise InputError("数据库外键检查失败，升级已回滚，请保留备份")
            if version < SCHEMA_VERSION:
                con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        with self.connect() as con:
            con.execute("PRAGMA journal_mode=WAL")

    @staticmethod
    def _check_version(con):
        version = con.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise InputError(f"数据库版本 {version} 高于当前支持的 {SCHEMA_VERSION}，请使用新版 LedgerDesk")
        if version == 0 and con.execute(
                "SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' LIMIT 1").fetchone():
            raise InputError("数据库未标记版本且包含已有表，拒绝自动接管；请使用独立数据目录")
        return version

    @staticmethod
    def _create_v1(con):
        # Execute DDL individually: executescript would commit the outer transaction.
        schema = """
                CREATE TABLE IF NOT EXISTS batches (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL,
                    is_sample INTEGER NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS imports (
                    id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batches(id),
                    side TEXT NOT NULL, filename TEXT NOT NULL, file_sha256 TEXT NOT NULL,
                    mapping TEXT NOT NULL, row_count INTEGER NOT NULL, created_at TEXT NOT NULL,
                    UNIQUE(batch_id, side, file_sha256));
                CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY, import_id TEXT NOT NULL REFERENCES imports(id),
                    line INTEGER NOT NULL, channel TEXT NOT NULL, order_id TEXT NOT NULL,
                    transaction_id TEXT NOT NULL, kind TEXT NOT NULL, amount_cents INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS entries_import ON entries(import_id);
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batches(id),
                    input_sha256 TEXT NOT NULL, created_at TEXT NOT NULL, summary TEXT NOT NULL,
                    UNIQUE(batch_id, input_sha256));
                CREATE TABLE IF NOT EXISTS results (
                    run_id TEXT NOT NULL REFERENCES runs(id), case_key TEXT NOT NULL,
                    evidence_sha256 TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(run_id, case_key));
                CREATE TABLE IF NOT EXISTS reviews (
                    batch_id TEXT NOT NULL REFERENCES batches(id), case_key TEXT NOT NULL,
                    evidence_sha256 TEXT NOT NULL, status TEXT NOT NULL, note TEXT NOT NULL,
                    updated_at TEXT NOT NULL, PRIMARY KEY(batch_id, case_key, evidence_sha256));
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batches(id),
                    action TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);

            """
        for statement in schema.split(";"):
            if statement.strip():
                con.execute(statement)

    def _migrate(self, con, version):
        if version == 1:
            # Original CSV bytes / ignored columns were never stored in 0.1.0.
            # Preserve history without claiming its currency was revalidated.
            con.execute("ALTER TABLE imports ADD COLUMN currency_policy TEXT NOT NULL DEFAULT 'legacy_unverified'")
        elif version == 2:
            con.execute("""CREATE TABLE imports_new (
                id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batches(id),
                side TEXT NOT NULL, filename TEXT NOT NULL, file_sha256 TEXT NOT NULL,
                mapping TEXT NOT NULL, row_count INTEGER NOT NULL, created_at TEXT NOT NULL,
                currency_policy TEXT NOT NULL DEFAULT 'legacy_unverified',
                is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
                revoked_at TEXT, revoked_reason TEXT NOT NULL DEFAULT '',
                replaces_id TEXT REFERENCES imports(id))""")
            con.execute("""INSERT INTO imports_new(id,batch_id,side,filename,file_sha256,mapping,
                row_count,created_at,currency_policy)
                SELECT id,batch_id,side,filename,file_sha256,mapping,row_count,created_at,currency_policy
                FROM imports ORDER BY rowid""")
            con.execute("DROP TABLE imports")
            con.execute("ALTER TABLE imports_new RENAME TO imports")
            con.execute("CREATE UNIQUE INDEX active_import_hash ON imports(batch_id,side,file_sha256) WHERE is_active=1")
            con.execute("ALTER TABLE batches ADD COLUMN input_revision INTEGER NOT NULL DEFAULT 0")
        elif version == 3:
            con.execute("ALTER TABLE imports ADD COLUMN channel_aliases TEXT NOT NULL DEFAULT '{}'")
            con.execute("""CREATE TABLE mapping_templates (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, side TEXT NOT NULL,
                mapping TEXT NOT NULL, channel_aliases TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                UNIQUE(name, side))""")
        else:
            raise InputError(f"没有数据库版本 {version} 的升级路径")

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=20)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            with con:
                yield con
        finally:
            con.close()

    @staticmethod
    def batch(con, batch_id):
        batch = con.execute("SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
        if batch is None:
            raise InputError("批次不存在")
        return dict(batch)

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
            return [dict(row) for row in con.execute("""
                SELECT b.*, (SELECT COUNT(*) FROM imports i WHERE i.batch_id=b.id AND i.is_active=1) AS file_count,
                  (SELECT MAX(created_at) FROM runs r WHERE r.batch_id=b.id) AS last_run
                FROM batches b ORDER BY b.created_at DESC,b.rowid DESC
            """)]

    @staticmethod
    def normalize_aliases(aliases):
        if aliases is None:
            return {}
        if not isinstance(aliases, dict) or len(aliases) > 100:
            raise InputError("渠道别名须为不超过 100 项的 JSON 对象")
        normalized = {}
        for source, target in aliases.items():
            if not isinstance(source, str) or not isinstance(target, str):
                raise InputError("渠道别名的键和值都必须是文本")
            source, target = source.strip(), target.strip()
            if not source or not target or len(source) > 128 or len(target) > 128:
                raise InputError("渠道别名的键和值须为 1～128 个字符")
            if any(ord(char) < 32 for char in source + target):
                raise InputError("渠道别名不能包含控制字符")
            normalized[source] = target
        return normalized

    def list_templates(self, side=None):
        with self.connect() as con:
            query, args = "SELECT * FROM mapping_templates", ()
            if side:
                query += " WHERE side=?"
                args = (side,)
            query += " ORDER BY updated_at DESC, name"
            return [dict(row) for row in con.execute(query, args)]

    def save_template(self, name, side, mapping, channel_aliases=None):
        name = require_text(name, "模板名称", 80)
        if side not in ("orders", "payments") or not isinstance(mapping, dict):
            raise InputError("模板数据无效")
        aliases = self.normalize_aliases(channel_aliases)
        timestamp = now()
        with self.connect() as con:
            template_id = identifier()
            con.execute("""INSERT INTO mapping_templates
                (id,name,side,mapping,channel_aliases,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(name,side) DO UPDATE SET mapping=excluded.mapping,
                channel_aliases=excluded.channel_aliases,updated_at=excluded.updated_at""",
                (template_id, name, side, json.dumps(mapping, ensure_ascii=False, sort_keys=True),
                 json.dumps(aliases, ensure_ascii=False, sort_keys=True), timestamp, timestamp))
            return dict(con.execute("SELECT * FROM mapping_templates WHERE name=? AND side=?", (name, side)).fetchone())

    def delete_template(self, template_id):
        with self.connect() as con:
            if con.execute("DELETE FROM mapping_templates WHERE id=?", (template_id,)).rowcount != 1:
                raise InputError("映射模板不存在")
        return {"deleted": True, "id": template_id}

    @staticmethod
    def source_fingerprint(con, batch_id):
        revision = Store.batch(con, batch_id)["input_revision"]
        files = list(con.execute("SELECT id,file_sha256,mapping,channel_aliases FROM imports WHERE batch_id=? AND is_active=1 ORDER BY id", (batch_id,)))
        return digest({"engine": RECONCILIATION_VERSION, "revision": revision,
                       "files": [tuple(row) for row in files]})

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
            self.batch(con, batch_id)
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
            record["channel"] = aliases.get(record["channel"], record["channel"])
        if replace_id is not None:
            replace_id = require_text(replace_id, "被替换文件", 64)
            reason = require_text(reason, "替换原因", 500)
        with self.connect() as con:
            # Serialize check+insert: repeated or concurrent requests cannot add twice.
            con.execute("BEGIN IMMEDIATE")
            self.batch(con, batch_id)
            if replace_id:
                original = self.active_import(con, batch_id, replace_id, side)
            previous = con.execute("SELECT id,row_count,mapping FROM imports WHERE batch_id=? AND side=? AND file_sha256=? AND is_active=1",
                                   (batch_id, side, file_hash)).fetchone()
            if previous:
                if replace_id and previous["id"] != replace_id:
                    raise InputError("替换文件已作为另一份有效文件导入，请先核实文件关系")
                if json.loads(previous["mapping"]) == mapping:
                    return {"id": previous["id"], "row_count": previous["row_count"], "duplicate": True}
                if not replace_id:
                    raise InputError("同一文件已按其他映射导入；请使用替换文件修正映射")
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
            con.executemany("INSERT INTO entries(import_id,line,channel,order_id,transaction_id,kind,amount_cents) VALUES(?,?,?,?,?,?,?)",
                [(import_id, row["line"], row["channel"], row["order_id"], row["transaction_id"],
                  row["kind"], row["amount_cents"]) for row in records])
            con.execute("UPDATE batches SET input_revision=input_revision+1 WHERE id=?", (batch_id,))
            self.audit(con, batch_id, "import_file", {"import_id": import_id, "side": side,
                       "filename": filename, "file_sha256": file_hash, "rows": len(records)})
            if replace_id:
                self.audit(con, batch_id, "replace_import", {"import_id": replace_id, "filename": original["filename"],
                           "replacement_id": import_id, "replacement_filename": filename, "reason": reason, "backup": backup})
        return {"id": import_id, "row_count": len(records), "duplicate": False}

    def reconcile(self, batch_id):
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self.batch(con, batch_id)
            files = [dict(row) for row in con.execute("SELECT * FROM imports WHERE batch_id=? AND is_active=1 ORDER BY id", (batch_id,))]
            if {row["side"] for row in files} != {"orders", "payments"}:
                raise InputError("请先分别导入业务单和支付账单")
            fingerprint = self.source_fingerprint(con, batch_id)
            old = con.execute("SELECT id FROM runs WHERE batch_id=? AND input_sha256=?", (batch_id, fingerprint)).fetchone()
            if old:
                return {"run_id": old["id"], "reused": True}
            rows = [dict(row) for row in con.execute("""
                SELECT e.*,i.side,i.filename FROM entries e JOIN imports i ON e.import_id=i.id
                WHERE i.batch_id=? AND i.is_active=1 ORDER BY e.id
            """, (batch_id,))]
            grouped = defaultdict(lambda: {"orders": [], "payments": []})
            duplicates = Counter((row["channel"], row["transaction_id"]) for row in rows if row["side"] == "payments")
            transaction_rows = defaultdict(list)
            for row in rows:
                if row["side"] == "payments":
                    transaction_rows[(row["channel"], row["transaction_id"])].append(row)
            latest = con.execute("SELECT id FROM runs WHERE batch_id=? ORDER BY rowid DESC LIMIT 1", (batch_id,)).fetchone()
            previous = {row["case_key"]: json.loads(row["payload"]) for row in con.execute(
                "SELECT case_key,payload FROM results WHERE run_id=?", (latest["id"] if latest else "",))}
            for row in rows:
                grouped[(row["channel"], row["order_id"])][row["side"]].append(row)
            results = []
            summary = {"groups": len(grouped), "matched": 0, "issues": 0,
                       "expected_total": 0, "actual_total": 0, "order_rows": 0, "payment_rows": 0}
            for (channel, order_id), group in sorted(grouped.items()):
                orders, payments = group["orders"], group["payments"]
                expected = sum(row["amount_cents"] for row in orders)
                sales = sum(row["amount_cents"] for row in payments if row["kind"] == "sale")
                refunds = sum(row["amount_cents"] for row in payments if row["kind"] == "refund")
                actual = sales - refunds
                reasons = []
                if len(orders) > 1:
                    reasons.append("duplicate_order")
                if any(duplicates[(row["channel"], row["transaction_id"])] > 1 for row in payments):
                    reasons.append("duplicate_transaction")
                if not orders:
                    reasons.append("payment_only")
                elif not payments:
                    reasons.append("order_only")
                elif expected != actual:
                    reasons.append("amount_mismatch")
                if not reasons:
                    reasons = ["matched"]
                case_key = digest([channel, order_id])
                other_rows = {row["id"]: row for payment in payments
                              for row in transaction_rows[(channel, payment["transaction_id"])]
                              if row["order_id"] != order_id}
                conflicts = [other_rows[key] for key in sorted(other_rows)]
                source_evidence = digest([{key: row[key] for key in ("import_id", "line", "channel", "order_id",
                                         "transaction_id", "kind", "amount_cents")} for row in orders+payments+conflicts])
                last = previous.get(case_key)
                if last and last.get("source_evidence_sha256", last["evidence_sha256"]) == source_evidence:
                    evidence = last["evidence_sha256"]
                else:
                    # A new evidence generation prevents resurrecting a resolved
                    # review when inputs revert to a much older state.
                    evidence = digest([source_evidence, identifier()])
                result = {"case_key": case_key, "channel": channel, "order_id": order_id,
                          "expected": money(expected), "actual": money(actual), "difference": money(actual-expected),
                          "sales": money(sales), "refunds": money(refunds), "reasons": reasons,
                          "reason_labels": [LABELS[reason] for reason in reasons],
                          "order_count": len(orders), "payment_count": len(payments),
                          "evidence_sha256": evidence,
                          "source_evidence_sha256": source_evidence,
                          "duplicate_rows": [{"order_id": row["order_id"], "channel": row["channel"],
                                              "filename": row["filename"], "line": row["line"],
                                              "transaction_id": row["transaction_id"], "kind": row["kind"],
                                              "amount": money(row["amount_cents"])} for row in conflicts],
                          "rows": [{"side": row["side"], "filename": row["filename"], "line": row["line"],
                                    "transaction_id": row["transaction_id"], "kind": row["kind"],
                                    "amount": money(row["amount_cents"])} for row in orders+payments]}
                results.append(result)
                summary["matched" if reasons == ["matched"] else "issues"] += 1
                summary["expected_total"] += expected
                summary["actual_total"] += actual
                summary["order_rows"] += len(orders)
                summary["payment_rows"] += len(payments)
            summary["difference"] = money(summary["actual_total"]-summary["expected_total"])
            summary["expected_total"] = money(summary["expected_total"])
            summary["actual_total"] = money(summary["actual_total"])
            run_id = identifier()
            con.execute("INSERT INTO runs VALUES(?,?,?,?,?)", (run_id, batch_id, fingerprint, now(), json.dumps(summary)))
            con.executemany("INSERT INTO results VALUES(?,?,?,?)", [(run_id, row["case_key"], row["evidence_sha256"],
                              json.dumps(row, ensure_ascii=False)) for row in results])
            self.audit(con, batch_id, "reconcile", {"run_id": run_id, "summary": summary})
        return {"run_id": run_id, "reused": False}

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
        with self.connect() as con:
            self.batch(con, batch_id)
            return [dict(row) for row in con.execute(
                "SELECT id,created_at,summary,input_sha256 FROM runs WHERE batch_id=? ORDER BY rowid DESC LIMIT ?",
                (batch_id, max(1, min(int(limit), 100))))]

    def compare_runs(self, batch_id, older_id, newer_id):
        with self.connect() as con:
            self.batch(con, batch_id)
            def load(run_id):
                return {row["case_key"]: json.loads(row["payload"]) for row in con.execute(
                    "SELECT case_key,payload FROM results WHERE run_id=? AND run_id IN (SELECT id FROM runs WHERE batch_id=?)",
                    (run_id, batch_id))}
            older, newer = load(older_id), load(newer_id)
            added = [newer[key] for key in sorted(set(newer) - set(older))]
            removed = [older[key] for key in sorted(set(older) - set(newer))]
            changed = []
            fields = ("expected", "actual", "difference", "reasons", "source_evidence_sha256")
            for key in sorted(set(older) & set(newer)):
                if any(older[key].get(field) != newer[key].get(field) for field in fields):
                    changed.append({"before": older[key], "after": newer[key]})
            return {"older_id": older_id, "newer_id": newer_id,
                    "added": added, "removed": removed, "changed": changed,
                    "counts": {"added": len(added), "removed": len(removed), "changed": len(changed)}}

    def review(self, batch_id, case_key, evidence_hash, status, note):
        if not isinstance(status, str) or status not in REVIEW_LABELS:
            raise InputError("未知处理状态")
        if not isinstance(note, str) or len(note) > 1000:
            raise InputError("处理备注最多 1000 字符")
        if status == "resolved" and not note.strip():
            raise InputError("标记已处理时必须填写处理依据")
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self.batch(con, batch_id)
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

    def backup(self, destination):
        return self.backup_existing(self.path, destination)

    @classmethod
    def backup_existing(cls, path, destination):
        path = Path(path).resolve()
        if not path.is_file():
            raise InputError("备份源数据库不存在，请检查 --data-dir；未创建空数据库")
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=20)) as source:
            version = cls._check_version(source)
            if version == 0:
                raise InputError("备份源不是已初始化的 LedgerDesk 数据库")
            summary = {"schema_version": version,
                       "batches": source.execute("SELECT COUNT(*) FROM batches").fetchone()[0],
                       "entries": source.execute("SELECT COUNT(*) FROM entries").fetchone()[0]}
            cls._write_backup(source, path, destination)
            return summary

    @staticmethod
    def _write_backup(source, source_path, destination):
        destination = Path(destination).resolve()
        if destination == source_path or destination.exists():
            raise InputError("备份路径必须是尚不存在的新文件")
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Reserve the destination exclusively, so concurrent backups cannot
        # overwrite a file that appeared after the existence check.
        try:
            with destination.open("xb"):
                pass
        except FileExistsError:
            raise InputError("备份目标已存在，请选择新文件") from None
        try:
            with closing(sqlite3.connect(destination)) as target:
                source.backup(target)
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
