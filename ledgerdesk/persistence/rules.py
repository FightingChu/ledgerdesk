"""Append-only rule revisions; selection belongs to a batch, snapshots to runs."""
from ..domain.errors import InputError
from ..domain.rules import RulePolicy
from ..domain.values import identifier, now, require_text


class RuleRepository:
    @staticmethod
    def get(con, rule_id):
        if rule_id is None:
            return RulePolicy()
        if not isinstance(rule_id, str):
            raise InputError("规则标识无效", code="invalid_rule")
        row = con.execute("SELECT id,name,revision,tolerance_cents FROM rule_revisions WHERE id=?", (rule_id,)).fetchone()
        if row is None:
            raise InputError("规则版本不存在", code="not_found")
        return RulePolicy(**dict(row))

    @staticmethod
    def selected(con, batch_id):
        row = con.execute("SELECT rule_id FROM batches WHERE id=?", (batch_id,)).fetchone()
        if row is None:
            raise InputError("批次不存在", code="not_found")
        return RuleRepository.get(con, row[0])

    @staticmethod
    def create(con, name, tolerance_cents):
        name = require_text(name, "规则名称", 80)
        RulePolicy(tolerance_cents=tolerance_cents)
        revision = con.execute("SELECT COALESCE(MAX(revision),0)+1 FROM rule_revisions WHERE name=?", (name,)).fetchone()[0]
        key = identifier()
        con.execute("INSERT INTO rule_revisions VALUES(?,?,?,?,?)", (key, name, revision, tolerance_cents, now()))
        return RuleRepository.get(con, key).snapshot()

    @staticmethod
    def list(con):
        return [dict(row) for row in con.execute("SELECT * FROM rule_revisions ORDER BY created_at DESC,rowid DESC")]
