"""Compatibility entry points for the versioned standard CSV ingestion pipeline."""
from .domain.errors import InputError
from .domain.money import MAX_AMOUNT_CENTS, cents, money
from .domain.mappings import FIELDS, validate_mapping
from .ingestion.reading import MAX_BYTES, MAX_ROWS, decode_document, read_csv
from .ingestion.currency import CURRENCY_HEADERS, CNY_VALUES, currency_columns, currency_error, currency_summary
from .ingestion.mappings import ALIASES
from .adapters.registry import get_adapter


def decode_file(content):
    raw, text, _ = decode_document(content)
    return raw, text


def preview(side, content):
    return get_adapter().preview(side, content)


def parse(side, content, mapping):
    result = get_adapter().validate(side, content, mapping)
    if result["errors"]:
        raise InputError(f"发现 {len(result['errors'])} 行无效数据，整份文件未导入", result["errors"][:30])
    return result["file_sha256"], result["records"]
