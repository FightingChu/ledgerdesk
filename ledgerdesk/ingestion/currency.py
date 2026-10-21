"""One CNY policy shared by preview, preflight and final parsing."""
CURRENCY_HEADERS = {"currency", "currency_code", "币种", "货币", "货币种类"}
CNY_VALUES = {"CNY", "RMB", "人民币"}


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
        return "仅支持人民币 CNY / RMB / 人民币，请勿混入其他币种"
    return None


def currency_summary(headers, rows):
    columns = currency_columns(headers)
    values = sorted({row[column].strip() for _, row in rows for column in columns})
    errors = [{"line": line, "message": message} for line, row in rows
              if (message := currency_error(columns, row))]
    return {"columns": columns, "values": values[:20], "value_count": len(values), "defaulted": not columns,
            "effective": "CNY" if not errors else None, "valid": not errors,
            "error_count": len(errors), "errors": errors[:30]}
