"""Upgrade a temporary copy and compare all original columns without printing business data."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ledgerdesk.persistence.database import Database
from ledgerdesk.persistence.diagnostics import inspect_database
from ledgerdesk.store import Store


def verify(source):
    source = Path(source).resolve()
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as con:
        expected = {}
        for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            columns = [row[1] for row in con.execute('PRAGMA table_info("' + table.replace('"','""') + '")')]
            sql = 'SELECT ' + ','.join('"'+column.replace('"','""')+'"' for column in columns) + ' FROM "'+table.replace('"','""')+'" ORDER BY rowid'
            digest = hashlib.sha256()
            count = 0
            for row in con.execute(sql):
                digest.update(json.dumps(tuple(row), ensure_ascii=False, separators=(",", ":")).encode()); count += 1
            expected[table] = sql, digest.hexdigest(), count
    with tempfile.TemporaryDirectory(prefix="ledgerdesk-migration-") as directory:
        target = Path(directory) / "copy.sqlite3"
        Database.backup_existing(source, target)
        upgraded = Store(target)
        with upgraded.connect() as con:
            for table, (sql, wanted, count) in expected.items():
                digest = hashlib.sha256()
                for row in con.execute(sql):
                    digest.update(json.dumps(tuple(row), ensure_ascii=False, separators=(",", ":")).encode())
                if digest.hexdigest() != wanted:
                    raise ValueError("Original values changed in " + table)
        report = inspect_database(target)
        return {"preserved_original_columns": True, "original_counts": {key: value[2] for key,value in expected.items()},
                "schema_version": report["schema_version"], "status": report["status"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("source", type=Path)
    print(json.dumps(verify(parser.parse_args().source), indent=2))
