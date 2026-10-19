"""Resolve exact supported adapter identities; unknown formats never silently fall back."""
from ..domain.errors import InputError
from .base import InputAdapter
from .standard_csv import StandardCsvAdapter


def get_adapter(adapter_id="standard_csv", version=1) -> InputAdapter:
    if adapter_id != StandardCsvAdapter.id or type(version) is not int or version != StandardCsvAdapter.version:
        raise InputError("不支持此文件适配器或版本，请选择标准 CSV v1", code="unsupported_adapter")
    return StandardCsvAdapter()
