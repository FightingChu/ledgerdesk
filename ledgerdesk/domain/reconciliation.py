"""Order grouping, net receipts, duplicate evidence and review generations."""
from collections import Counter, defaultdict
from .money import money
from .values import digest

RECONCILIATION_VERSION = 3
LABELS = {"matched": "金额一致", "amount_mismatch": "金额不一致", "order_only": "仅业务单",
          "payment_only": "仅支付账单", "duplicate_order": "重复业务单", "duplicate_transaction": "重复流水"}
REVIEW_LABELS = {"pending": "待处理", "in_progress": "处理中", "resolved": "已处理"}


def build_reconciliation(rows, previous, generation):
    grouped = defaultdict(lambda: {"orders": [], "payments": []})
    duplicates = Counter((row["channel"], row["transaction_id"]) for row in rows if row["side"] == "payments")
    transaction_rows = defaultdict(list)
    for row in rows:
        if row["side"] == "payments":
            transaction_rows[(row["channel"], row["transaction_id"])].append(row)
    for row in rows:
        grouped[(row["channel"], row["order_id"])][row["side"]].append(row)
    results = []
    summary = {"groups": len(grouped), "matched": 0, "issues": 0,
               "expected_total": 0, "actual_total": 0, "order_rows": 0, "payment_rows": 0}
    for (channel, order_id), group in sorted(grouped.items()):
        orders, payments = group["orders"], group["payments"]
        expected = sum(row["amount_cents"] for row in orders)
        sales = sum(row["amount_cents"] for row in payments if row["kind"] == "sale")
        refunds = sum(row["amount_cents"] for row in payments if row["kind"] == "refund")
        actual = sales - refunds
        reasons = []
        if len(orders) > 1:
            reasons.append("duplicate_order")
        if any(duplicates[(row["channel"], row["transaction_id"])] > 1 for row in payments):
            reasons.append("duplicate_transaction")
        if not orders:
            reasons.append("payment_only")
        elif not payments:
            reasons.append("order_only")
        elif expected != actual:
            reasons.append("amount_mismatch")
        if not reasons:
            reasons = ["matched"]
        case_key = digest([channel, order_id])
        other_rows = {row["id"]: row for payment in payments
                      for row in transaction_rows[(channel, payment["transaction_id"])]
                      if row["order_id"] != order_id}
        conflicts = [other_rows[key] for key in sorted(other_rows)]
        source_evidence = digest([{key: row[key] for key in ("import_id", "line", "channel", "order_id",
                                 "transaction_id", "kind", "amount_cents")} for row in orders+payments+conflicts])
        last = previous.get(case_key)
        if last and last.get("source_evidence_sha256", last["evidence_sha256"]) == source_evidence:
            evidence = last["evidence_sha256"]
        else:
            # A new evidence generation prevents resurrecting a resolved
            # review when inputs revert to a much older state.
            evidence = digest([source_evidence, generation])
        result = {"case_key": case_key, "channel": channel, "order_id": order_id,
                  "expected": money(expected), "actual": money(actual), "difference": money(actual-expected),
                  "sales": money(sales), "refunds": money(refunds), "reasons": reasons,
                  "reason_labels": [LABELS[reason] for reason in reasons],
                  "order_count": len(orders), "payment_count": len(payments),
                  "evidence_sha256": evidence,
                  "source_evidence_sha256": source_evidence,
                  "duplicate_rows": [{"order_id": row["order_id"], "channel": row["channel"],
                                      "filename": row["filename"], "line": row["line"],
                                      "transaction_id": row["transaction_id"], "kind": row["kind"],
                                      "amount": money(row["amount_cents"])} for row in conflicts],
                  "rows": [{"side": row["side"], "filename": row["filename"], "line": row["line"],
                            "channel": row["channel"], "source_channel": row.get("source_channel"),
                            "transaction_id": row["transaction_id"], "kind": row["kind"],
                            "amount": money(row["amount_cents"])} for row in orders+payments]}
        results.append(result)
        summary["matched" if reasons == ["matched"] else "issues"] += 1
        summary["expected_total"] += expected
        summary["actual_total"] += actual
        summary["order_rows"] += len(orders)
        summary["payment_rows"] += len(payments)
    summary["difference"] = money(summary["actual_total"]-summary["expected_total"])
    summary["expected_total"] = money(summary["expected_total"])
    summary["actual_total"] = money(summary["actual_total"])
    return results, summary
