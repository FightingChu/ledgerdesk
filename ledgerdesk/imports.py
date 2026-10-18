"""Strict, atomic CSV parsing and exact CNY amount conversion."""
import base64
import binascii
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import io
import re

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 10000
MAX_AMOUNT_CENTS = 10**12
CURRENCY_HEADERS = {"currency", "currency_code", "币种", "货币", "货币种类"}
CNY_VALUES = {"CNY", "RMB", "人民币"}
FIELDS = {
    "orders": ("order_id", "amount", "channel"),
    "payments": ("order_id", "transaction_id", "amount", "event_type", "channel"),
}
ALIASES = {
    "order_id": ("order_id", "订单号", "商户订单号", "业务单号"),
    "transaction_id": ("transaction_id", "交易流水号", "流水号", "渠道流水号"),
    "amount": ("amount", "金额", "金额（元）", "金额(元)", "预计净到账", "预计净到账(元)"),
    "event_type": ("event_type", "类型", "交易类型", "收支类型"),
    "channel": ("channel", "渠道", "支付渠道"),
}


class InputError(ValueError):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or []


def cents(value):
    text = str(value).strip()
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", text):
        raise InputError("金额须为非负十进制元，最多两位小数；不接受千分位或科学计数法")
    try:
        amount = int(Decimal(text) * 100)
    except (InvalidOperation, ValueError):
        raise InputError("金额无法解析") from None
    if amount > MAX_AMOUNT_CENTS:
        raise InputError("单行金额超过首版上限 100 亿元")
    return amount


def money(value):
    sign = "-" if value < 0 else ""
    return f"{sign}{abs(value)//100:,}.{abs(value)%100:02d}"


def decode_file(content):
    if not isinstance(content, str) or len(content) > MAX_BYTES * 4 // 3 + 16:
        raise InputError("文件超过 5 MiB 上限")
    try:
        raw = base64.b64decode(content, validate=True)
    except (ValueError, binascii.Error):
        raise InputError("文件编码无效，请重新选择 CSV") from None
    if not raw or len(raw) > MAX_BYTES:
        raise InputError("文件为空或超过 5 MiB 上限")
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise InputError("文件须为 UTF-8 或 GB18030 编码")
    if "\x00" in text:
        raise InputError("文件包含二进制内容，请导出标准 CSV")
    return raw, text


def read_csv(text):
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(reader, None)
        if header is None:
            raise InputError("CSV 缺少表头")
        headers = [value.strip() for value in header]
        if not all(headers) or len(headers) != len(set(headers)) or len(headers) > 80:
            raise InputError("表头不能空白或重名，最多 80 列")
        rows = []
        for row in reader:
            line = reader.line_num
            if not row or not any(value.strip() for value in row):
                continue
            if len(row) != len(headers):
                raise InputError(f"第 {line} 行列数与表头不一致")
            if any(len(value) > 2048 for value in row):
                raise InputError(f"第 {line} 行存在超过 2048 字符的字段")
            rows.append((line, dict(zip(headers, row))))
            if len(rows) > MAX_ROWS:
                raise InputError("首版单文件最多 10000 行")
    except csv.Error as exc:
        raise InputError("CSV 格式错误：" + str(exc)) from None
    if not rows:
        raise InputError("CSV 只有表头，没有数据")
    return headers, rows


def currency_columns(headers):
    return [header for header in headers if header.casefold() in CURRENCY_HEADERS]


def currency_error(columns, row):
    values = [row[column].strip().upper() for column in columns]
    if any(not value for value in values):
        return "币种列不可空白；仅在没有币种列时默认人民币"
    normalized = {"CNY" if value in CNY_VALUES else value for value in values}
    if len(normalized) > 1:
        return "同一行的多个币种列相互冲突"
    if normalized and normalized != {"CNY"}:
        return "首版仅支持人民币 CNY / RMB / 人民币，请勿混入其他币种"
    return None


def currency_summary(headers, rows):
    columns = currency_columns(headers)
    values = sorted({row[column].strip() for _, row in rows for column in columns})
    errors = [{"line": line, "message": message} for line, row in rows
              if (message := currency_error(columns, row))]
    return {"columns": columns, "values": values[:20], "value_count": len(values), "defaulted": not columns,
            "effective": "CNY" if not errors else None, "valid": not errors,
            "error_count": len(errors), "errors": errors[:30]}


def preview(side, content):
    if not isinstance(side, str) or side not in FIELDS:
        raise InputError("未知数据类型")
    raw, text = decode_file(content)
    headers, rows = read_csv(text)
    normalized = {header.casefold(): header for header in headers}
    mapping = {}
    for field in FIELDS[side]:
        mapping[field] = next((normalized[name.casefold()] for name in ALIASES[field]
                               if name.casefold() in normalized), "")
    return {"headers": headers, "rows": [row for _, row in rows[:5]],
            "row_count": len(rows), "mapping": mapping,
            "file_sha256": hashlib.sha256(raw).hexdigest(), "currency": currency_summary(headers, rows)}


def parse(side, content, mapping):
    if not isinstance(side, str) or side not in FIELDS or not isinstance(mapping, dict):
        raise InputError("数据类型或字段映射无效")
    raw, text = decode_file(content)
    headers, rows = read_csv(text)
    selected = [mapping.get(field) for field in FIELDS[side]]
    if any(name not in headers for name in selected) or len(set(selected)) != len(selected):
        raise InputError("请为每个字段选择不同的 CSV 列")
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
    if errors:
        raise InputError(f"发现 {len(errors)} 行无效数据，整份文件未导入", errors[:30])
    return hashlib.sha256(raw).hexdigest(), parsed
