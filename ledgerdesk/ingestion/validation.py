"""Complete row validation with bounded inputs and no database effects."""
from ..domain.errors import InputError
from ..domain.money import cents
from ..domain.mappings import FIELDS
from .currency import currency_columns, currency_error


def validate_rows(side, headers, rows, mapping):
    parsed, errors = [], []
    columns = currency_columns(headers)
    for line, row in rows:
        try:
            error = currency_error(columns, row)
            if error:
                raise InputError(error)
            data = {field: row[mapping[field]].strip() for field in FIELDS[side]}
            for field in ("order_id", "channel", "transaction_id"):
                if field in data and (not data[field] or len(data[field]) > 128 or
                                      any(ord(c) < 32 for c in data[field])):
                    raise InputError("订单号、渠道、流水号须为 1～128 个字符，且不能含控制字符")
            amount = cents(data["amount"])
            kind = "expected"
            if side == "payments":
                label = data["event_type"].casefold()
                types = {"sale": "sale", "收款": "sale", "支付": "sale",
                         "refund": "refund", "退款": "refund"}
                if label not in types:
                    raise InputError("账单类型仅接受 sale / refund / 收款 / 支付 / 退款")
                kind = types[label]
            parsed.append({"line": line, "order_id": data["order_id"],
                           "channel": data["channel"], "amount_cents": amount,
                           "transaction_id": data.get("transaction_id", ""), "kind": kind,
                           "currency_policy": "explicit_cny" if columns else "default_cny"})
        except InputError as exc:
            errors.append({"line": line, "message": str(exc)})
    return parsed, errors
