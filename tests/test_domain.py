"""Domain rules exercise amounts and evidence without a database or HTTP server."""
import ast
from pathlib import Path
import unittest
from ledgerdesk.domain.errors import InputError
from ledgerdesk.domain.filters import ResultFilter
from ledgerdesk.domain.money import cents
from ledgerdesk.domain.reconciliation import build_reconciliation


class DomainTests(unittest.TestCase):
    def test_split_rules_keep_net_receipts_and_evidence_stable(self):
        def row(number, side, amount, kind, transaction=""):
            return {"id": number, "import_id": side, "line": number + 1, "channel": "wx", "order_id": "0001",
                    "side": side, "amount_cents": amount, "kind": kind, "transaction_id": transaction,
                    "filename": side + ".csv", "source_channel": "微信"}
        rows = [row(1, "orders", 8000, "expected"), row(2, "payments", 10000, "sale", "P1"),
                row(3, "payments", 2000, "refund", "R1")]
        result, summary = build_reconciliation(rows, {}, "first")
        self.assertEqual(result[0]["reasons"], ["matched"])
        self.assertEqual(summary["actual_total"], "80.00")
        again, _ = build_reconciliation(rows, {result[0]["case_key"]: result[0]}, "second")
        self.assertEqual(result[0]["evidence_sha256"], again[0]["evidence_sha256"])
        self.assertEqual(cents("10000000000.00"), 10**12)
        with self.assertRaises(InputError):
            cents("10000000000.01")

    def test_domain_imports_do_not_depend_on_infrastructure(self):
        domain = Path(__file__).resolve().parent.parent / "ledgerdesk/domain"
        for file in domain.glob("*.py"):
            tree = ast.parse(file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                    self.assertFalse(any(name.split(".")[0] in ("sqlite3", "http", "server", "persistence", "application")
                                         for name in names), file.name)
