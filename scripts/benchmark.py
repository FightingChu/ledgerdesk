"""Reproducible local synthetic timing and traced-allocation measurements."""
import argparse
import base64
import json
from pathlib import Path
import platform
import sys
import tempfile
import time
import tracemalloc

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ledgerdesk.store import Store
from ledgerdesk.imports import preview
from ledgerdesk.application.statistics import StatisticsService
from ledgerdesk.application.reporting import ReportingService


def measure(groups):
    if not 1 <= groups <= 100000:
        raise ValueError("Benchmark supports 1..100000 synthetic groups")
    with tempfile.TemporaryDirectory(prefix="ledgerdesk-benchmark-") as directory:
        store = Store(Path(directory) / "bench.sqlite3"); batch = store.create_batch("SYNTHETIC benchmark", is_sample=True)
        start = time.perf_counter()
        for offset in range(0, groups, 10000):
            indices = range(offset, min(groups, offset + 10000))
            for side in ("orders", "payments"):
                text = ("order_id,amount,channel\n" + "\n".join(f"SYN{i:08},1.01,c{i%5}" for i in indices)) if side == "orders" else (
                    "order_id,transaction_id,amount,event_type,channel\n" + "\n".join(f"SYN{i:08},P{i},1.00,sale,c{i%5}" for i in indices))
                data = base64.b64encode(text.encode()).decode()
                store.import_file(batch, side, side + ".csv", data, preview(side, data)["mapping"])
        imported = time.perf_counter() - start
        phases = {}
        for name, operation in (("reconcile", lambda: store.reconcile(batch)), ("page", lambda: store.result_page(batch, page_size=50)),
                ("statistics", lambda: StatisticsService(store).batch(batch)),
                ("csv", lambda: sum(len(chunk) for chunk in ReportingService(store).stream(batch)))):
            tracemalloc.start(); before = time.perf_counter()
            value = operation(); elapsed = time.perf_counter() - before
            _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
            phases[name] = {"seconds": round(elapsed, 6), "peak_python_bytes": peak}
            if name == "csv":
                phases[name]["output_bytes"] = value
        return {"groups": groups, "import_seconds": round(imported, 6), "phases": phases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[5000]); parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = {"format": "ledgerdesk.synthetic-benchmark", "version": 1, "python": platform.python_version(),
              "platform": platform.system(), "synthetic": True, "results": [measure(size) for size in args.sizes]}
    data = json.dumps(report, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8") as output:
            output.write(data + "\n")
    print(data)


if __name__ == "__main__":
    main()
