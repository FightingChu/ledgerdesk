"""Create a source release from an explicit, reviewed file list."""
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent.parent
# Never glob user files: even CSVs under samples/ can contain private data.
RELEASE_FILES = (
    ".gitignore", "LICENSE", "README.md", "pyproject.toml", "start.cmd", "config.example.json",
    "ledgerdesk/__init__.py", "ledgerdesk/__main__.py", "ledgerdesk/imports.py",
    "ledgerdesk/store.py", "ledgerdesk/server.py", "ledgerdesk/static/index.html",
    "ledgerdesk/config.py", "ledgerdesk/persistence/diagnostics.py", "ledgerdesk/application/data_management.py",
    "ledgerdesk/domain/__init__.py", "ledgerdesk/domain/errors.py",
    "ledgerdesk/domain/values.py", "ledgerdesk/domain/money.py", "ledgerdesk/domain/mappings.py",
    "ledgerdesk/domain/reconciliation.py", "ledgerdesk/domain/filters.py", "ledgerdesk/domain/history.py",
    "ledgerdesk/persistence/__init__.py", "ledgerdesk/persistence/database.py",
    "ledgerdesk/persistence/migrations.py", "ledgerdesk/persistence/templates.py", "ledgerdesk/persistence/runs.py",
    "ledgerdesk/persistence/result_queries.py", "ledgerdesk/domain/result_summary.py",
    "ledgerdesk/application/__init__.py", "ledgerdesk/application/reconciliation.py", "ledgerdesk/application/reports.py",
    "ledgerdesk/static/app.js", "ledgerdesk/static/data.js", "ledgerdesk/static/results.js", "ledgerdesk/static/style.css",
    "samples/orders.csv", "samples/payments.csv", "scripts/build_release.py", "scripts/verify_release.py",
    "tests/__init__.py", "tests/test_product.py", "tests/test_reliability.py", "tests/test_import_management.py",
    "tests/test_workflows.py", "tests/test_domain.py", "tests/test_config.py", "tests/test_data_management.py", "tests/test_pagination.py",
    "tests/fixtures/schema_v1.sql", "tests/fixtures/schema_v4.sql", "tests/fixtures/schema_v5.sql", "docs/PRODUCT.md", "docs/FEEDBACK_TEMPLATE.md",
    "docs/CHANGELOG.md", "docs/PROJECT_PLAN.md", "docs/ARCHITECTURE.md", "docs/DATA_MANAGEMENT.md", "docs/PAGINATION.md", ".github/workflows/test.yml",
    "ledgerdesk/domain/reviews.py",
    "ledgerdesk/application/batches.py",
    "ledgerdesk/application/imports.py",
    "ledgerdesk/application/reviews.py",
    "ledgerdesk/persistence/batches.py",
    "ledgerdesk/persistence/imports.py",
    "ledgerdesk/persistence/reviews.py",
    "ledgerdesk/persistence/audit.py",
    "ledgerdesk/static/batches.js",
    "ledgerdesk/static/reviews.js",
    "ledgerdesk/static/audit.js",
    "tests/test_bulk_reviews.py",
    "tests/test_audit.py",
    "tests/test_review_migration.py",
    "tests/test_review_http.py",
    "tests/fixtures/schema_v6.sql",
    "docs/BULK_REVIEWS.md",
    "ledgerdesk/ingestion/__init__.py",
    "ledgerdesk/ingestion/reading.py",
    "ledgerdesk/ingestion/currency.py",
    "ledgerdesk/ingestion/mappings.py",
    "ledgerdesk/ingestion/validation.py",
    "ledgerdesk/adapters/__init__.py",
    "ledgerdesk/adapters/base.py",
    "ledgerdesk/adapters/registry.py",
    "ledgerdesk/adapters/standard_csv.py",
    "ledgerdesk/application/import_validation.py",
    "ledgerdesk/static/import.js",
    "tests/test_ingestion.py",
    "tests/test_import_validation.py",
    "tests/test_import_validation_http.py",
    "tests/fixtures/schema_v7.sql",
    "docs/IMPORT_WIZARD.md",
)


def main():
    tree = ast.parse((ROOT / "ledgerdesk/__init__.py").read_text(encoding="utf-8"))
    version = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                   and any(isinstance(name, ast.Name) and name.id == "__version__" for name in node.targets))
    selected = [(name, (ROOT / name).read_bytes()) for name in sorted(RELEASE_FILES)]
    timestamp = datetime.fromtimestamp(int(os.environ["SOURCE_DATE_EPOCH"]), timezone.utc) \
        if "SOURCE_DATE_EPOCH" in os.environ else datetime.now(timezone.utc)
    if not 1980 <= timestamp.year <= 2107:
        raise ValueError("ZIP timestamp must be between 1980 and 2107")
    out = ROOT / "dist"
    out.mkdir(exist_ok=True)
    archive = out / f"LedgerDesk-{version}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        for name, data in selected:
            entry = zipfile.ZipInfo("LedgerDesk/" + name, date_time=timestamp.timetuple()[:6])
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            zipped.writestr(entry, data)
    with zipfile.ZipFile(archive) as zipped:
        assert set(zipped.namelist()) == {"LedgerDesk/" + name for name in RELEASE_FILES}
        assert zipped.testzip() is None
        for name, data in selected:
            assert zipped.read("LedgerDesk/" + name) == data
    result = {"version": version, "archive": archive.name, "files": len(selected), "bytes": archive.stat().st_size,
              "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "includes_runtime_data": False}
    (out/"release.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
