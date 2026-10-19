"""Immutable source projections for bounded evidence queries."""
import json
from .errors import InputError


def evidence_values(run_id, result):
    for kind, key in (("source", "rows"), ("duplicate", "duplicate_rows")):
        for position, row in enumerate(result.get(key, []), 1):
            yield run_id, result["case_key"], kind, position, json.dumps(row, ensure_ascii=False)


def validate_kind(kind):
    if kind not in ("source", "duplicate"):
        raise InputError("证据类型无效", code="invalid_input")
    return kind
