"""Real loopback requests with lifecycle cleanup and explicit session credentials."""
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from ledgerdesk.server import make_server
from .workspace import WorkspaceTest


class HttpWorkspaceTest(WorkspaceTest):
    def setUp(self):
        super().setUp()
        self.server = make_server(self.store.path, 0)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.addCleanup(self.close_server)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.token = self.request("/api/bootstrap")[1]["token"]

    def close_server(self):
        self.server.shutdown(); self.server.server_close(); self.server_thread.join()

    def request(self, path, payload=None, headers=None):
        values = {} if payload is None else {"Content-Type": "application/json", "X-LedgerDesk-Token": self.token}
        values.update(headers or {})
        try:
            response = urlopen(Request(self.base + path, None if payload is None else json.dumps(payload).encode(), values), timeout=20)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            return response.status, json.loads(raw) if response.headers.get("Content-Type", "").startswith("application/json") else raw, response.headers
