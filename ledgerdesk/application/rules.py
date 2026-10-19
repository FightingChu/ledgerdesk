"""Rule creation and selection with immutable revisions and explicit audit."""
from ..persistence.rules import RuleRepository


class RuleService:
    def __init__(self, store):
        self.store = store

    def list(self):
        with self.store.connect() as con:
            return RuleRepository.list(con)

    def create(self, name, tolerance_cents):
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            return RuleRepository.create(con, name, tolerance_cents)

    def select(self, batch_id, rule_id):
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self.store.require_editable(con, batch_id)
            selected = RuleRepository.get(con, rule_id)
            con.execute("UPDATE batches SET rule_id=? WHERE id=?", (rule_id, batch_id))
            self.store.audit(con, batch_id, "select_rule", selected.snapshot())
            return selected.snapshot()
