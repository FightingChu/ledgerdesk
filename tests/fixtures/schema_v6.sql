BEGIN TRANSACTION;
CREATE TABLE audit (
                    id INTEGER PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batches(id),
                    action TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE batches (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL,
                    is_sample INTEGER NOT NULL, created_at TEXT NOT NULL, input_revision INTEGER NOT NULL DEFAULT 0, tags TEXT NOT NULL DEFAULT '[]', archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)));
CREATE TABLE entries (
                    id INTEGER PRIMARY KEY, import_id TEXT NOT NULL REFERENCES imports(id),
                    line INTEGER NOT NULL, channel TEXT NOT NULL, order_id TEXT NOT NULL,
                    transaction_id TEXT NOT NULL, kind TEXT NOT NULL, amount_cents INTEGER NOT NULL, source_channel TEXT);
CREATE TABLE "imports" (
                id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batches(id),
                side TEXT NOT NULL, filename TEXT NOT NULL, file_sha256 TEXT NOT NULL,
                mapping TEXT NOT NULL, row_count INTEGER NOT NULL, created_at TEXT NOT NULL,
                currency_policy TEXT NOT NULL DEFAULT 'legacy_unverified',
                is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
                revoked_at TEXT, revoked_reason TEXT NOT NULL DEFAULT '',
                replaces_id TEXT REFERENCES imports(id), channel_aliases TEXT NOT NULL DEFAULT '{}');
CREATE TABLE mapping_templates (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, side TEXT NOT NULL,
                mapping TEXT NOT NULL, channel_aliases TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
                UNIQUE(name, side));
CREATE TABLE result_lookup (
        run_id TEXT NOT NULL, case_key TEXT NOT NULL, position INTEGER NOT NULL,
        evidence_sha256 TEXT NOT NULL, search_text TEXT NOT NULL,
        matched INTEGER NOT NULL CHECK(matched IN (0,1)), reason_tokens TEXT NOT NULL,
        snapshot_status TEXT, snapshot_note TEXT NOT NULL, summary TEXT NOT NULL,
        PRIMARY KEY(run_id,case_key), UNIQUE(run_id,position),
        FOREIGN KEY(run_id,case_key) REFERENCES results(run_id,case_key));
CREATE TABLE results (
                    run_id TEXT NOT NULL REFERENCES runs(id), case_key TEXT NOT NULL,
                    evidence_sha256 TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(run_id, case_key));
CREATE TABLE reviews (
                    batch_id TEXT NOT NULL REFERENCES batches(id), case_key TEXT NOT NULL,
                    evidence_sha256 TEXT NOT NULL, status TEXT NOT NULL, note TEXT NOT NULL,
                    updated_at TEXT NOT NULL, PRIMARY KEY(batch_id, case_key, evidence_sha256));
CREATE TABLE runs (
                    id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batches(id),
                    input_sha256 TEXT NOT NULL, created_at TEXT NOT NULL, summary TEXT NOT NULL,
                    UNIQUE(batch_id, input_sha256));
CREATE INDEX entries_import ON entries(import_id);
CREATE UNIQUE INDEX active_import_hash ON imports(batch_id,side,file_sha256) WHERE is_active=1;
COMMIT;
PRAGMA user_version=6;
