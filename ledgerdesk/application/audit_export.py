"""Local-only audit exports with deterministic columns and UTF-8 BOM."""
import csv
import io
import json
from ..domain.audit_export import validate_export
from ..persistence.audit_export import AuditExportRepository


class AuditExportService:
    def __init__(self, store):
        self.store = store

    def stream(self, batch_id, action="all", output_format="csv", until_id=None):
        options = validate_export(action, output_format, until_id)
        with self.store.connect() as con:
            con.execute("BEGIN")
            rows = AuditExportRepository.rows(con, batch_id, options["action"], options["until_id"])
            if output_format == "json":
                for row in rows:
                    yield (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
                return
            output = io.StringIO(newline="")
            writer = csv.writer(output)
            writer.writerow(["事件ID", "操作类型", "操作", "发生时间UTC", "事件上限", "事件内容JSON"])
            yield b"\xef\xbb\xbf" + output.getvalue().encode("utf-8")
            output.seek(0)
            output.truncate(0)
            for row in rows:
                writer.writerow([row["id"], row["action"], row["label"], row["created_at"], row["until_id"],
                                 json.dumps(row["payload"], ensure_ascii=False, separators=(",", ":"))])
                if output.tell() >= 32 * 1024:
                    yield output.getvalue().encode("utf-8")
                    output.seek(0)
                    output.truncate(0)
            if output.tell():
                yield output.getvalue().encode("utf-8")
