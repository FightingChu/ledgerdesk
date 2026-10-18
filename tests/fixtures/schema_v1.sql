
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
                PRAGMA user_version=1;
