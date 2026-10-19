"""A clean, temporary localhost workflow with no dependency on user data."""
import json
from pathlib import Path
import sys
import tempfile
import threading
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ledgerdesk.server import make_server


def main():
    with tempfile.TemporaryDirectory(prefix="ledgerdesk-smoke-") as directory:
        server = make_server(Path(directory) / "test.sqlite3", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urlopen(base + "/api/bootstrap", timeout=20) as response:
                bootstrap = json.load(response)
            request = Request(base + "/api/demo", b"{}", {"Content-Type": "application/json", "X-LedgerDesk-Token": bootstrap["token"]})
            with urlopen(request, timeout=20) as response:
                batch = json.load(response)["batch_id"]
            with urlopen(base + f"/api/batches/{batch}/statistics", timeout=20) as response:
                stats = json.load(response)
            assert stats["totals"]["groups"] == 7 and stats["totals"]["issues"] == 5
            with urlopen(base + f"/api/batches/{batch}/report?format=html", timeout=20) as response:
                assert b"</html>" in response.read()
            print(json.dumps({"version": bootstrap["version"], "synthetic": True, "groups": 7, "issues": 5, "status": "ok"}))
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == "__main__":
    main()
