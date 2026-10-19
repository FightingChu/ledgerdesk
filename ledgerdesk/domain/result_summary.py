"""A compact, immutable projection for lists without source-line arrays."""
import json


def lookup_values(run_id, position, payload):
    summary = {key: value for key, value in payload.items()
               if key not in ("rows", "duplicate_rows")}
    summary["source_count"] = len(payload.get("rows", []))
    summary["duplicate_count"] = len(payload.get("duplicate_rows", []))
    snapshot = payload.get("review_snapshot") or {}
    return (run_id, payload["case_key"], position, payload["evidence_sha256"],
            (payload["order_id"] + " " + payload["channel"]).lower(),
            int(payload["reasons"] == ["matched"]), "|" + "|".join(payload["reasons"]) + "|",
            snapshot.get("status"), snapshot.get("note", ""), json.dumps(summary, ensure_ascii=False))
