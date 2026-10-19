"""Immutable named report profile revisions."""
import json
from ..domain.report_profiles import validate_columns, DEFAULT_COLUMNS
from ..domain.errors import InputError
from ..domain.values import identifier, now, require_text


class ReportProfileRepository:
    @staticmethod
    def get(con, profile_id=None):
        if profile_id is None:
            return {"id": None, "name": "默认报告", "revision": 0, "columns": list(DEFAULT_COLUMNS)}
        if not isinstance(profile_id, str):
            raise InputError("报告配置无效", code="invalid_report")
        row = con.execute("SELECT * FROM report_profiles WHERE id=?", (profile_id,)).fetchone()
        if row is None:
            raise InputError("报告配置不存在", code="not_found")
        result = dict(row)
        result["columns"] = json.loads(result["columns"])
        return result

    @staticmethod
    def list(con):
        return [ReportProfileRepository.get(con, row[0]) for row in con.execute("SELECT id FROM report_profiles ORDER BY rowid DESC")]

    @staticmethod
    def create(con, name, columns):
        name = require_text(name, "报告配置名称", 80)
        columns = validate_columns(columns)
        revision = con.execute("SELECT COALESCE(MAX(revision),0)+1 FROM report_profiles WHERE name=?", (name,)).fetchone()[0]
        key = identifier()
        con.execute("INSERT INTO report_profiles VALUES(?,?,?,?,?)", (key, name, revision, json.dumps(columns), now()))
        return ReportProfileRepository.get(con, key)
