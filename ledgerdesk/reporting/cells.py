"""Translate compact results into user-visible report values."""
from ..domain.reconciliation import REVIEW_LABELS


def cell(key, row, context):
    rule = row.get("rule_snapshot")
    if key == "nature":
        return "合成样例" if context["batch"]["is_sample"] else "用户导入（来源未核验）"
    if key == "reasons":
        return " / ".join(row["reason_labels"])
    if key == "review_status":
        return "无需处理" if row["reasons"] == ["matched"] else REVIEW_LABELS.get(row["review_status"], "未记录")
    if key == "run_time":
        return context["run"]["created_at"]
    if key == "run_id":
        return context["run"]["id"]
    if key in ("rule", "rule_revision", "tolerance_cents"):
        return rule.get({"rule": "name", "rule_revision": "revision", "tolerance_cents": "tolerance_cents"}[key], "未记录") if rule else "未记录"
    value = row.get(key, "")
    return value.replace(",", "") if key in ("expected", "actual", "difference", "sales", "refunds") else value
