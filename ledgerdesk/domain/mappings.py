"""Explicit field selection and single-step channel aliases."""
from .errors import InputError
from .values import require_text

FIELDS = {
    "orders": ("order_id", "amount", "channel"),
    "payments": ("order_id", "transaction_id", "amount", "event_type", "channel"),
}


def validate_mapping(side, mapping):
    if not isinstance(side, str) or side not in FIELDS or not isinstance(mapping, dict):
        raise InputError("模板数据侧或字段映射无效", code="invalid_mapping")
    if set(mapping) != set(FIELDS[side]):
        raise InputError("映射必须包含当前数据侧的全部标准字段", code="invalid_mapping")
    columns = list(mapping.values())
    if any(not isinstance(value, str) or not value.strip() or len(value) > 2048
           or any(ord(char) < 32 for char in value) for value in columns):
        raise InputError("映射列名不能为空白、包含控制字符或超长", code="invalid_mapping")
    if len(set(columns)) != len(columns):
        raise InputError("每个标准字段必须选择不同的列", code="invalid_mapping")
    return dict(mapping)


def normalize_aliases(aliases):
    if aliases is None:
        return {}
    if not isinstance(aliases, dict) or len(aliases) > 100:
        raise InputError("渠道别名须为不超过 100 项的对象", code="invalid_aliases")
    result = {}
    for source, target in aliases.items():
        source = require_text(source, "原渠道", 128)
        target = require_text(target, "目标渠道", 128)
        if any(ord(char) < 32 for char in source + target) or source in result:
            raise InputError("渠道别名包含控制字符或去空白后重复的原渠道", code="invalid_aliases")
        result[source] = target
    return result
