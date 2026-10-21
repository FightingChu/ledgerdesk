"""Exact conversion between CNY decimal yuan and integer cents."""
from decimal import Decimal, InvalidOperation
import re
from .errors import InputError

MAX_AMOUNT_CENTS = 10**12


def cents(value):
    text = str(value).strip()
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", text):
        raise InputError("金额须为非负十进制元，最多两位小数；不接受千分位或科学计数法")
    try:
        amount = int(Decimal(text) * 100)
    except (InvalidOperation, ValueError):
        raise InputError("金额无法解析") from None
    if amount > MAX_AMOUNT_CENTS:
        raise InputError("单行金额超过上限 100 亿元")
    return amount


def money(value):
    sign = "-" if value < 0 else ""
    return f"{sign}{abs(value)//100:,}.{abs(value)%100:02d}"
