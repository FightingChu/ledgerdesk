"""Transactional schema upgrades; version numbers are advanced only after validation."""
from ..domain.errors import InputError
from ..domain.result_summary import lookup_values
import json

SCHEMA_VERSION = 6


def check_version(con):
    version = con.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise InputError(f"数据库版本 {version} 高于当前支持的 {SCHEMA_VERSION}，请使用新版 LedgerDesk")
    if version == 0 and con.execute(
            "SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' LIMIT 1").fetchone():
        raise InputError("数据库未标记版本且包含已有表，拒绝自动接管；请使用独立数据目录")
    return version


def create_v1(con):
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


def migrate(con, version):
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
    elif version == 4:
        con.execute("ALTER TABLE entries ADD COLUMN source_channel TEXT")
        con.execute("ALTER TABLE mapping_templates ADD COLUMN revision INTEGER NOT NULL DEFAULT 1")
        con.execute("ALTER TABLE batches ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'")
        con.execute("ALTER TABLE batches ADD COLUMN archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1))")
    elif version == 5:
        con.execute("""CREATE TABLE result_lookup (
            run_id TEXT NOT NULL, case_key TEXT NOT NULL, position INTEGER NOT NULL,
            evidence_sha256 TEXT NOT NULL, search_text TEXT NOT NULL,
            matched INTEGER NOT NULL CHECK(matched IN (0,1)), reason_tokens TEXT NOT NULL,
            snapshot_status TEXT, snapshot_note TEXT NOT NULL, summary TEXT NOT NULL,
            PRIMARY KEY(run_id,case_key), UNIQUE(run_id,position),
            FOREIGN KEY(run_id,case_key) REFERENCES results(run_id,case_key))""")
        position, last_run = 0, None
        for run_id, payload in con.execute("SELECT run_id,payload FROM results ORDER BY run_id,rowid"):
            if last_run != run_id:
                position, last_run = 0, run_id
            position += 1
            con.execute("INSERT INTO result_lookup VALUES(?,?,?,?,?,?,?,?,?,?)",
                        lookup_values(run_id, position, json.loads(payload)))
    else:
        raise InputError(f"没有数据库版本 {version} 的升级路径")
