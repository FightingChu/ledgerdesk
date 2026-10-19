"""Schema v9: versioned rules, compact metrics/evidence, report profiles and saved filters."""
import json
from ..domain.metrics import metric_values
from ..domain.evidence import evidence_values


def upgrade(con):
    statements = [
        """CREATE TABLE rule_revisions(id TEXT PRIMARY KEY,name TEXT NOT NULL,revision INTEGER NOT NULL,
           tolerance_cents INTEGER NOT NULL CHECK(tolerance_cents BETWEEN 0 AND 1000000),created_at TEXT NOT NULL,
           UNIQUE(name,revision))""",
        "ALTER TABLE batches ADD COLUMN rule_id TEXT REFERENCES rule_revisions(id)",
        "ALTER TABLE runs ADD COLUMN rule_snapshot TEXT",
        """CREATE TABLE result_metrics(run_id TEXT NOT NULL,case_key TEXT NOT NULL,channel TEXT NOT NULL,
           expected INTEGER NOT NULL,actual INTEGER NOT NULL,difference INTEGER NOT NULL,sales INTEGER NOT NULL,
           refunds INTEGER NOT NULL,PRIMARY KEY(run_id,case_key),
           FOREIGN KEY(run_id,case_key) REFERENCES results(run_id,case_key))""",
        "CREATE INDEX metrics_channel ON result_metrics(run_id,channel,case_key)",
        """CREATE TABLE result_sources(run_id TEXT NOT NULL,case_key TEXT NOT NULL,kind TEXT NOT NULL,
           position INTEGER NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(run_id,case_key,kind,position),
           FOREIGN KEY(run_id,case_key) REFERENCES results(run_id,case_key))""",
        """CREATE TABLE report_profiles(id TEXT PRIMARY KEY,name TEXT NOT NULL,revision INTEGER NOT NULL,
           columns TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(name,revision))""",
        """CREATE TABLE saved_filters(id TEXT PRIMARY KEY,name TEXT NOT NULL UNIQUE,payload TEXT NOT NULL,
           revision INTEGER NOT NULL,updated_at TEXT NOT NULL)""",
    ]
    for statement in statements:
        con.execute(statement)
    for run_id, payload in con.execute("SELECT run_id,payload FROM results ORDER BY rowid"):
        result = json.loads(payload)
        con.execute("INSERT INTO result_metrics VALUES(?,?,?,?,?,?,?,?)", metric_values(run_id, result))
        con.executemany("INSERT INTO result_sources VALUES(?,?,?,?,?)", evidence_values(run_id, result))
