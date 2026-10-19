"""Ordered, versioned report columns do not change reconciliation results."""
from .errors import InputError

COLUMNS = {
    "nature": "数据性质", "channel": "渠道", "order_id": "订单号", "expected": "预计净到账(元)",
    "actual": "账单净额(元)", "difference": "差额(元)", "order_count": "业务单行数", "payment_count": "账单行数",
    "reasons": "核查结果", "review_status": "处理状态", "note": "处理备注", "run_time": "核对时间UTC",
    "sales": "收款(元)", "refunds": "退款(元)", "run_id": "核对版本", "rule": "规则名称",
    "rule_revision": "规则修订", "tolerance_cents": "容差(分)", "evidence_sha256": "证据指纹", "source_count": "源行数",
}
DEFAULT_COLUMNS = tuple(list(COLUMNS)[:12])


def validate_columns(columns):
    if (not isinstance(columns, list) or not 1 <= len(columns) <= len(COLUMNS)
            or any(not isinstance(key, str) or key not in COLUMNS for key in columns)
            or len(set(columns)) != len(columns)):
        raise InputError("报表列须为已知、不重复的有序字段列表", code="invalid_report")
    return list(columns)
