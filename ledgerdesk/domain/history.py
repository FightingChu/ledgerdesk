"""Compare saved reconciliation payloads without consulting live source rows."""


def compare_results(older, newer):
    old = {row["case_key"]: row for row in older}
    new = {row["case_key"]: row for row in newer}
    added = [new[key] for key in sorted(new.keys() - old.keys())]
    removed = [old[key] for key in sorted(old.keys() - new.keys())]
    changes = []
    fields = ("expected", "actual", "difference", "reasons", "source_evidence_sha256", "rule_snapshot")
    for key in sorted(old.keys() & new.keys()):
        changed = [field for field in fields if old[key].get(field) != new[key].get(field)]
        if ("review_snapshot" in old[key] and "review_snapshot" in new[key]
                and old[key]["review_snapshot"] != new[key]["review_snapshot"]):
            changed.append("review_snapshot")
        if changed:
            changes.append({"before": old[key], "after": new[key], "changed_fields": changed})
    return {"added": added, "removed": removed, "changed": changes,
            "counts": {"added": len(added), "removed": len(removed), "changed": len(changes)}}
