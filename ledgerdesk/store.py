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

SCHEMA_VERSION = 2

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
            con.execute("BEGIN IMMEDIATE")
            version = self._check_version(con)
            if version == 0:
                self._create_v1(con)
            elif version < SCHEMA_VERSION:
                self.backup(self.path.with_name(
                    self.path.name + f".pre-v{version}-to-v{SCHEMA_VERSION}-{identifier()}.sqlite3"))
            for previous in range(version or 1, SCHEMA_VERSION):
                self._migrate(con, previous)
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
            con.execute("INSERT INTO batches VALUES(?,?,?,?,?)",
                        (batch_id, name, description.strip(), int(is_sample), now()))
            self.audit(con, batch_id, "create_batch", {"is_sample": bool(is_sample)})
        return batch_id

    def list_batches(self):
        with self.connect() as con:
            return [dict(row) for row in con.execute("""
                SELECT b.*, (SELECT COUNT(*) FROM imports i WHERE i.batch_id=b.id) AS file_count,
                  (SELECT MAX(created_at) FROM runs r WHERE r.batch_id=b.id) AS last_run
                FROM batches b ORDER BY b.created_at DESC,b.rowid DESC
            """)]

    def import_file(self, batch_id, side, filename, content, mapping):
        filename = require_text(filename, "文件名", 200)
        file_hash, records = parse(side, content, mapping)
        with self.connect() as con:
            # Serialize check+insert: repeated or concurrent requests cannot add twice.
            con.execute("BEGIN IMMEDIATE")
            self.batch(con, batch_id)
            previous = con.execute("SELECT id,row_count,mapping FROM imports WHERE batch_id=? AND side=? AND file_sha256=?",
                                   (batch_id, side, file_hash)).fetchone()
            if previous:
                if json.loads(previous["mapping"]) != mapping:
                    raise InputError("同一文件已按其他映射导入；请新建批次修正映射")
                return {"id": previous["id"], "row_count": previous["row_count"], "duplicate": True}
            import_id = identifier()
            con.execute("INSERT INTO imports(id,batch_id,side,filename,file_sha256,mapping,row_count,created_at,currency_policy) VALUES(?,?,?,?,?,?,?,?,?)",
                        (import_id, batch_id, side, filename, file_hash,
                         json.dumps(mapping, ensure_ascii=False), len(records), now(), records[0]["currency_policy"]))
            con.executemany("INSERT INTO entries(import_id,line,channel,order_id,transaction_id,kind,amount_cents) VALUES(?,?,?,?,?,?,?)",
                [(import_id, row["line"], row["channel"], row["order_id"], row["transaction_id"],
                  row["kind"], row["amount_cents"]) for row in records])
            self.audit(con, batch_id, "import_file", {"import_id": import_id, "side": side,
                       "filename": filename, "file_sha256": file_hash, "rows": len(records)})
        return {"id": import_id, "row_count": len(records), "duplicate": False}

    def reconcile(self, batch_id):
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self.batch(con, batch_id)
            files = [dict(row) for row in con.execute("SELECT * FROM imports WHERE batch_id=? ORDER BY id", (batch_id,))]
            if {row["side"] for row in files} != {"orders", "payments"}:
                raise InputError("请先分别导入业务单和支付账单")
            fingerprint = digest([(row["id"], row["file_sha256"], row["mapping"]) for row in files])
            old = con.execute("SELECT id FROM runs WHERE batch_id=? AND input_sha256=?", (batch_id, fingerprint)).fetchone()
            if old:
                return {"run_id": old["id"], "reused": True}
            rows = [dict(row) for row in con.execute("""
                SELECT e.*,i.side,i.filename FROM entries e JOIN imports i ON e.import_id=i.id
                WHERE i.batch_id=? ORDER BY e.id
            """, (batch_id,))]
            grouped = defaultdict(lambda: {"orders": [], "payments": []})
            duplicates = Counter((row["channel"], row["transaction_id"]) for row in rows if row["side"] == "payments")
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
                evidence = digest([{key: row[key] for key in ("import_id", "line", "channel", "order_id",
                                         "transaction_id", "kind", "amount_cents")} for row in orders+payments])
                result = {"case_key": case_key, "channel": channel, "order_id": order_id,
                          "expected": money(expected), "actual": money(actual), "difference": money(actual-expected),
                          "sales": money(sales), "refunds": money(refunds), "reasons": reasons,
                          "reason_labels": [LABELS[reason] for reason in reasons],
                          "order_count": len(orders), "payment_count": len(payments),
                          "evidence_sha256": evidence,
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
            batch = self.batch(con, batch_id)
            files = [dict(row) for row in con.execute("SELECT id,side,filename,file_sha256,row_count,created_at,currency_policy FROM imports WHERE batch_id=? ORDER BY rowid", (batch_id,))]
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
            source = [dict(row) for row in con.execute("SELECT id,file_sha256,mapping FROM imports WHERE batch_id=? ORDER BY id", (batch_id,))]
            stale = bool(latest and latest["input_sha256"] != digest([(r["id"], r["file_sha256"], r["mapping"]) for r in source]))
            audit = [dict(row) for row in con.execute("SELECT action,payload,created_at FROM audit WHERE batch_id=? ORDER BY id DESC LIMIT 50", (batch_id,))]
            return {"batch": batch, "imports": files, "run": ({"id": latest["id"], "created_at": latest["created_at"],
                    "summary": json.loads(latest["summary"])} if latest else None),
                    "results": results, "stale": stale, "audit": audit}

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
            source = list(con.execute("SELECT id,file_sha256,mapping FROM imports WHERE batch_id=? ORDER BY id", (batch_id,)))
            if not latest or latest["input_sha256"] != digest([tuple(row) for row in source]):
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
        destination = Path(destination).resolve()
        if destination == self.path or destination.exists():
            raise InputError("备份路径必须是尚不存在的新文件")
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Reserve the destination exclusively, so concurrent backups cannot
        # overwrite a file that appeared after the existence check.
        try:
            with destination.open("xb"):
                pass
        except FileExistsError:
            raise InputError("备份目标已存在，请选择新文件") from None
        with self.connect() as source:
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
            finally:
                target.close()
