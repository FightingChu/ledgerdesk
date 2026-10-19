"""Classify two compact results while retaining the historical comparison contract."""


def classify(before, after):
    if before is None:
        return {"kind": "added", "after": after}
    if after is None:
        return {"kind": "removed", "before": before}
    fields = [name for name in ("expected", "actual", "difference", "reasons", "source_evidence_sha256",
              "rule_snapshot") if before.get(name) != after.get(name)]
    if "review_snapshot" in before and "review_snapshot" in after and before["review_snapshot"] != after["review_snapshot"]:
        fields.append("review_snapshot")
    return {"kind": "changed", "before": before, "after": after, "changed_fields": fields} if fields else None
