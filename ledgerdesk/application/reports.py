"""CSV reporting with exact amounts and spreadsheet formula escaping."""
import csv
import io
from ..domain.errors import InputError
from ..domain.reconciliation import REVIEW_LABELS


def safe_cell(value):
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def export_csv(detail, rows=None):
    if not detail["run"]:
        raise InputError("请先执行核对")
    if detail["stale"]:
        raise InputError("数据有更新，请重新核对后再导出")
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(["数据性质", "渠道", "订单号", "预计净到账(元)", "账单净额(元)", "差额(元)",
                     "业务单行数", "账单行数", "核查结果", "处理状态", "处理备注", "核对时间UTC"])
    for row in detail["results"] if rows is None else rows:
        writer.writerow(["演示批次" if detail["batch"]["is_sample"] else "用户导入（来源未核验）",
            safe_cell(row["channel"]), safe_cell(row["order_id"]), row["expected"].replace(",", ""),
            row["actual"].replace(",", ""), row["difference"].replace(",", ""), row["order_count"], row["payment_count"],
            " / ".join(row["reason_labels"]), "无需处理" if row["reasons"] == ["matched"] else REVIEW_LABELS[row["review_status"]],
            safe_cell(row["note"]), detail["run"]["created_at"]])
    return out.getvalue().encode("utf-8-sig")
