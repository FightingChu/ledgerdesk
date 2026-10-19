"""Review commands and optimistic revision validation, independent of storage."""
from .errors import InputError
from .reconciliation import REVIEW_LABELS
from .values import require_text

MAX_BULK_REVIEWS = 100


def validate_review(status, note):
    if not isinstance(status, str) or status not in REVIEW_LABELS:
        raise InputError("未知处理状态")
    if not isinstance(note, str) or len(note) > 1000:
        raise InputError("处理备注最多 1000 字符")
    if status == "resolved" and not note.strip():
        raise InputError("标记已处理时必须填写处理依据")
    return note.strip()


def validate_revision(value):
    if type(value) is not int or not 0 <= value < 2**53:
        raise InputError("须提供非负整数处理版本，请刷新结果", code="invalid_revision")
    return value


def validate_items(items):
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_BULK_REVIEWS:
        raise InputError("每次请选择 1～100 项差异", code="invalid_selection")
    result, seen = [], set()
    for item in items:
        if not isinstance(item, dict):
            raise InputError("所选差异格式无效", code="invalid_selection")
        key = require_text(item.get("case_key"), "差异标识", 128)
        evidence = require_text(item.get("evidence_sha256"), "证据版本", 128)
        revision = validate_revision(item.get("expected_revision"))
        if key in seen:
            raise InputError("不能重复选择同一项差异", code="invalid_selection")
        seen.add(key)
        result.append({"case_key": key, "evidence_sha256": evidence, "expected_revision": revision})
    return result
