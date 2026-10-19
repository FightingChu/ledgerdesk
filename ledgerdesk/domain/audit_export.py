"""Validate local audit exports without exposing filesystem or runtime paths."""
from .errors import InputError
from .values import require_text


FORMATS = ("csv", "json")


def validate_export(action="all", output_format="csv", until_id=None):
    if not isinstance(action, str) or action == "" or len(action) > 40:
        raise InputError("操作类型无效", code="invalid_filter")
    if output_format not in FORMATS:
        raise InputError("操作记录导出格式无效", code="invalid_export")
    if until_id is not None and (type(until_id) is not int or not 0 <= until_id < 2**63):
        raise InputError("操作记录范围无效", code="invalid_pagination")
    return {"action": action, "format": output_format, "until_id": until_id}
