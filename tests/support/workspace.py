"""A reusable synthetic workspace; tests never open the default business database."""
import base64
from pathlib import Path
import tempfile
import unittest
from ledgerdesk.store import Store
from ledgerdesk.domain.filters import ResultFilter


class WorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "test.sqlite3")
        self.batch = self.store.create_batch("synthetic expansion")

    def add(self, side, text, batch=None, **options):
        from ledgerdesk.imports import preview
        data = base64.b64encode(text.encode()).decode()
        return self.store.import_file(batch or self.batch, side, side + ".csv", data, preview(side, data)["mapping"], **options)

    def pair(self, expected="2", actual="1", count=3):
        self.add("orders", "order_id,amount,channel\n" + "\n".join(f"A{i:04},{expected},x" for i in range(count)))
        self.add("payments", "order_id,transaction_id,amount,event_type,channel\n" + "\n".join(f"A{i:04},P{i},{actual},sale,x" for i in range(count)))
        self.run = self.store.reconcile(self.batch)["run_id"]
        return self.store.result_page(self.batch, ResultFilter(), page_size=100)["items"]
