"""Whole-file import, revoke and atomic replacement workflows."""
import json
from ..domain.errors import InputError
from ..domain.values import identifier, require_text
from .import_validation import prepare_import
from ..persistence.imports import ImportRepository


class ImportService:
    def __init__(self, store):
        self.store = store

    def revoke(self, batch_id, import_id, reason):
        reason = require_text(reason, "撤销原因", 500)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self.store.require_editable(con, batch_id)
            original = ImportRepository.active(con, batch_id, import_id)
            backup = self.store.import_backup()
            ImportRepository.revoke(con, import_id, reason)
            ImportRepository.advance(con, batch_id)
            self.store.audit(con, batch_id, "revoke_import", {"import_id": import_id, "filename": original["filename"],
                             "reason": reason, "backup": backup})
        return {"revoked": True, "import_id": import_id}

    def add(self, batch_id, side, filename, content, mapping, replace_id=None, reason="", channel_aliases=None,
            adapter_id="standard_csv", adapter_version=1, receipt=None, approvals=None):
        report, identity = prepare_import(side, filename, content, mapping, replace_id, reason, channel_aliases,
                                          adapter_id, adapter_version)
        if report["errors"]:
            raise InputError(f"发现 {len(report['errors'])} 行无效数据，整份文件未导入", report["errors"][:30])
        file_hash, records = report["file_sha256"], report["records"]
        aliases = identity["channel_aliases"]
        filename, replace_id, reason = identity["filename"], identity["replace_id"], identity["reason"]
        for record in records:
            record["source_channel"] = record["channel"]
            record["channel"] = aliases.get(record["channel"], record["channel"])
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            batch = self.store.require_editable(con, batch_id)
            if receipt is not None:
                if approvals is None:
                    raise InputError("校验凭据不可用，请重新校验", code="stale_validation")
                approvals.verify(receipt, batch_id, batch["input_revision"], identity)
            if replace_id:
                original = ImportRepository.active(con, batch_id, replace_id, side)
            previous = ImportRepository.previous(con, batch_id, side, file_hash)
            if previous:
                if replace_id and previous["id"] != replace_id:
                    raise InputError("替换文件已作为另一份有效文件导入，请先核实文件关系")
                if json.loads(previous["mapping"]) == mapping and json.loads(previous["channel_aliases"]) == aliases:
                    return {"id": previous["id"], "row_count": previous["row_count"], "duplicate": True}
                if not replace_id:
                    raise InputError("同一文件已按其他映射或渠道别名导入；请使用替换文件修正", code="conflict")
            backup = None
            if replace_id:
                backup = self.store.import_backup()
                ImportRepository.revoke(con, replace_id, reason)
            import_id = identifier()
            ImportRepository.insert(con, import_id, batch_id, side, filename, file_hash, mapping, records, replace_id, aliases, identity["adapter_id"], identity["adapter_version"])
            ImportRepository.advance(con, batch_id)
            self.store.audit(con, batch_id, "import_file", {"import_id": import_id, "side": side,
                             "filename": filename, "file_sha256": file_hash, "rows": len(records), "adapter": report["adapter"]})
            if replace_id:
                self.store.audit(con, batch_id, "replace_import", {"import_id": replace_id, "filename": original["filename"],
                    "replacement_id": import_id, "replacement_filename": filename, "reason": reason, "backup": backup})
        return {"id": import_id, "row_count": len(records), "duplicate": False}
