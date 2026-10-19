"""Version 1 of the existing LedgerDesk CNY CSV contract."""
import hashlib
from ..domain.errors import InputError
from ..domain.mappings import FIELDS, validate_mapping
from ..ingestion.reading import decode_document, read_csv
from ..ingestion.currency import currency_summary
from ..ingestion.mappings import mapping_diagnostics
from ..ingestion.validation import validate_rows


class StandardCsvAdapter:
    id = "standard_csv"
    version = 1
    name = "标准 CSV"

    def document(self, side, content):
        if not isinstance(side, str) or side not in FIELDS:
            raise InputError("未知数据类型")
        raw, text, encoding = decode_document(content)
        headers, rows = read_csv(text)
        return {"headers": headers, "source_rows": rows, "file_sha256": hashlib.sha256(raw).hexdigest(),
                "encoding": encoding, "adapter": {"id": self.id, "version": self.version, "name": self.name}}

    def preview(self, side, content):
        document = self.document(side, content)
        rows = document.pop("source_rows")
        return {**document, "rows": [row for _, row in rows[:5]], "row_count": len(rows),
                **mapping_diagnostics(side, document["headers"]), "currency": currency_summary(document["headers"], rows)}

    def validate(self, side, content, mapping):
        validate_mapping(side, mapping)
        document = self.document(side, content)
        headers, rows = document["headers"], document.pop("source_rows")
        if any(column not in headers for column in mapping.values()):
            raise InputError("请为每个字段选择不同的 CSV 列", code="invalid_mapping")
        records, errors = validate_rows(side, headers, rows, mapping)
        return {**document, "records": records, "errors": errors, "row_count": len(rows),
                "currency": currency_summary(headers, rows)}
