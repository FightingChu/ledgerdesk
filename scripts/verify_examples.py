"""Validate published configuration examples and independently authored golden input syntax."""
import base64
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ledgerdesk.domain.backup_policy import validate_policy
from ledgerdesk.domain.report_profiles import validate_columns
from ledgerdesk.imports import preview, parse


def main():
    validate_policy(json.loads((ROOT / "examples/backup-policy.json").read_text()))
    validate_columns(json.loads((ROOT / "examples/report-columns.json").read_text()))
    scenarios = 0
    for directory in (ROOT / "tests/golden").iterdir():
        if not directory.is_dir():
            continue
        for side in ("orders", "payments"):
            data = base64.b64encode((directory / (side + ".csv")).read_bytes()).decode()
            parse(side, data, preview(side, data)["mapping"])
        scenarios += 1
    print("Published examples passed; synthetic golden scenarios:", scenarios)


if __name__ == "__main__":
    main()
