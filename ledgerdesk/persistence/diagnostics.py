"""Read-only, content-free SQLite diagnostics for the schemas we can restore."""
from contextlib import closing
from pathlib import Path
import sqlite3
from .. import __version__
from .migrations import SCHEMA_VERSION

REQUIRED_COLUMNS = {
    "batches": {"id", "name", "description", "is_sample", "created_at"},
    "imports": {"id", "batch_id", "side", "filename", "file_sha256", "mapping", "row_count", "created_at"},
    "entries": {"id", "import_id", "line", "channel", "order_id", "transaction_id", "kind", "amount_cents"},
    "runs": {"id", "batch_id", "input_sha256", "created_at", "summary"},
    "results": {"run_id", "case_key", "evidence_sha256", "payload"},
    "reviews": {"batch_id", "case_key", "evidence_sha256", "status", "note", "updated_at"},
    "audit": {"id", "batch_id", "action", "payload", "created_at"},
}


def inspect_database(path):
    """Never initialize/migrate a source or include its names, notes, or local paths."""
    path = Path(path).resolve()
    report = {"format": "ledgerdesk.database-diagnostics", "version": 1, "application_version": __version__,
              "supported_schema": SCHEMA_VERSION, "schema_version": None, "status": "missing",
              "integrity": "not_checked", "foreign_key_violations": None, "counts": {}, "bytes": 0}
    if not path.is_file():
        return report
    try:
        report["bytes"] = path.stat().st_size
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=20)) as con:
            con.execute("PRAGMA query_only=ON")
            con.execute("PRAGMA trusted_schema=OFF")
            con.execute("BEGIN")
            version = con.execute("PRAGMA user_version").fetchone()[0]
            report["schema_version"] = version
            if version > SCHEMA_VERSION:
                report["status"] = "unsupported"
                return report
            if version < 1:
                report["status"] = "invalid"
                return report
            expected = {name: set(columns) for name, columns in REQUIRED_COLUMNS.items()}
            if version >= 2:
                expected["imports"].add("currency_policy")
            if version >= 3:
                expected["imports"].update(("is_active", "revoked_at", "revoked_reason", "replaces_id"))
                expected["batches"].add("input_revision")
            if version >= 4:
                expected["imports"].add("channel_aliases")
                expected["mapping_templates"] = {"id", "name", "side", "mapping", "channel_aliases", "created_at", "updated_at"}
            if version >= 5:
                expected["entries"].add("source_channel")
                expected["mapping_templates"].add("revision")
                expected["batches"].update(("tags", "archived"))
            if version >= 6:
                expected["result_lookup"] = {"run_id", "case_key", "position", "evidence_sha256", "search_text",
                                             "matched", "reason_tokens", "snapshot_status", "snapshot_note", "summary"}
            actual_tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table, columns in expected.items():
                if table not in actual_tables or not columns.issubset({row[1] for row in con.execute("PRAGMA table_info(" + table + ")")}):
                    report["status"] = "invalid"
                    return report
            # Report only the check outcome, never the values from a damaged row.
            integrity = [row[0] for row in con.execute("PRAGMA integrity_check(10)")]
            report["integrity"] = "ok" if integrity == ["ok"] else "failed"
            report["foreign_key_violations"] = sum(1 for _ in con.execute("PRAGMA foreign_key_check"))
            report["counts"] = {table: con.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] for table in expected}
            report["status"] = "ok" if report["integrity"] == "ok" and report["foreign_key_violations"] == 0 else "invalid"
            if version >= 6:
                report["index_coverage"] = report["counts"]["result_lookup"] == report["counts"]["results"]
                if not report["index_coverage"]:
                    report["status"] = "invalid"
    except (sqlite3.Error, OSError):
        report["status"] = "invalid"
    return report
