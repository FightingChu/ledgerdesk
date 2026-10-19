"""Schema v10: durable local jobs, backup registry and workspace preferences."""


def upgrade(con):
    for statement in (
        """CREATE TABLE jobs(id TEXT PRIMARY KEY,kind TEXT NOT NULL,batch_id TEXT REFERENCES batches(id),
          payload TEXT NOT NULL,dedupe_key TEXT UNIQUE,state TEXT NOT NULL,attempt INTEGER NOT NULL,
          progress INTEGER NOT NULL,total INTEGER NOT NULL,phase TEXT NOT NULL,cancel_requested INTEGER NOT NULL,
          created_at TEXT NOT NULL,updated_at TEXT NOT NULL,result TEXT,error TEXT NOT NULL)""",
        "CREATE INDEX jobs_queue ON jobs(state,created_at,id)",
        """CREATE TABLE preferences(key TEXT PRIMARY KEY,payload TEXT NOT NULL,revision INTEGER NOT NULL)""",
        """CREATE TABLE managed_backups(id TEXT PRIMARY KEY,sha256 TEXT NOT NULL,created_at TEXT NOT NULL)""",
    ):
        con.execute(statement)
