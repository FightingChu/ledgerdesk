"""Strict scalar query parameters shared by feature routes."""
from ..domain.errors import InputError


def single(query, name, default=None):
    values = query.get(name, [default])
    if len(values) != 1:
        raise InputError("查询参数不能重复")
    return values[0]


def integer(query, name, default, maximum=10**9):
    value = single(query, name, str(default))
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal() or len(value) > 12:
        raise InputError("分页参数无效", code="invalid_pagination")
    number = int(value)
    if not 1 <= number <= maximum:
        raise InputError("分页参数无效", code="invalid_pagination")
    return number


def paging(query):
    return integer(query, "page", 1), integer(query, "page_size", 25, 100)


def boolean(query, name, default=False):
    value = single(query, name, "true" if default else "false")
    if value not in ("true", "false"):
        raise InputError("布尔查询参数无效")
    return value == "true"
