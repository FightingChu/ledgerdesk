"""Saved filter payloads share the result query contract."""
from dataclasses import asdict
from .filters import ResultFilter
from .errors import InputError


def validate_preset(value):
    if not isinstance(value, dict) or set(value) - {"group", "reason", "status", "q"}:
        raise InputError("筛选配置字段无效", code="invalid_filter")
    return asdict(ResultFilter(**value))
