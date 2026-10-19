"""Read-only import diagnostics and short-lived approvals for the exact effective input."""
import base64
import csv
import hashlib
import hmac
import io
import json
import secrets
import time
from ..adapters.registry import get_adapter
from ..domain.errors import InputError
from ..domain.mappings import normalize_aliases
from ..domain.values import digest, require_text
from ..persistence.imports import ImportRepository
from ..persistence.result_queries import ResultQueryRepository
from .reports import safe_cell


def prepare_import(side, filename, content, mapping, replace_id=None, reason="", channel_aliases=None,
                   adapter_id="standard_csv", adapter_version=1):
    filename = require_text(filename, "文件名", 200)
    aliases = normalize_aliases(channel_aliases)
    if replace_id is not None:
        replace_id = require_text(replace_id, "被替换文件", 64)
        reason = require_text(reason, "替换原因", 500)
    else:
        reason = ""
    report = get_adapter(adapter_id, adapter_version).validate(side, content, mapping)
    identity = {"side": side, "filename": filename, "file_sha256": report["file_sha256"],
                "mapping": dict(mapping), "channel_aliases": aliases, "replace_id": replace_id, "reason": reason,
                "adapter_id": report["adapter"]["id"], "adapter_version": report["adapter"]["version"]}
    return report, identity


class ValidationApprovals:
    ttl = 600

    def __init__(self):
        self.secret = secrets.token_bytes(32)

    @staticmethod
    def fingerprint(batch_id, revision, identity):
        return digest({"batch_id": batch_id, "input_revision": revision, "input": identity})

    def issue(self, batch_id, revision, identity):
        body = base64.urlsafe_b64encode(json.dumps({"fingerprint": self.fingerprint(batch_id, revision, identity),
            "expires": int(time.time()) + self.ttl}, sort_keys=True).encode()).decode()
        return body + "." + hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()

    def verify(self, receipt, batch_id, revision, identity):
        try:
            if not isinstance(receipt, str) or len(receipt) > 1024:
                raise ValueError
            body, signature = receipt.split(".")
            expected = hmac.new(self.secret, body.encode("ascii"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, signature):
                raise ValueError
            payload = json.loads(base64.b64decode(body, altchars=b"-_", validate=True))
            if not isinstance(payload, dict) or type(payload.get("expires")) is not int:
                raise ValueError
            if payload["expires"] <= time.time() or payload.get("fingerprint") != self.fingerprint(batch_id, revision, identity):
                raise ValueError
        except (ValueError, TypeError, UnicodeError, KeyError):
            raise InputError("校验已失效或输入已变化，请返回字段步骤重新校验", code="stale_validation") from None


class ImportValidationService:
    def __init__(self, store):
        self.store = store
        self.approvals = ValidationApprovals()

    def check(self, batch_id, payload, download=False):
        page, size = payload.get("page", 1), payload.get("page_size", 25)
        ResultQueryRepository.validate_page(page, size)
        report, identity = prepare_import(payload.get("side"), payload.get("filename"), payload.get("content"),
            payload.get("mapping"), payload.get("replace_id"), payload.get("reason", ""), payload.get("channel_aliases"),
            payload.get("adapter_id", "standard_csv"), payload.get("adapter_version", 1))
        with self.store.connect() as con:
            con.execute("BEGIN")
            batch = self.store.require_editable(con, batch_id)
            if identity["replace_id"]:
                ImportRepository.active(con, batch_id, identity["replace_id"], identity["side"])
            receipt = None if report["errors"] else self.approvals.issue(batch_id, batch["input_revision"], identity)
        if download:
            output = io.StringIO(newline="")
            writer = csv.writer(output)
            writer.writerow(["CSV行号", "校验问题"])
            writer.writerows([error["line"], safe_cell(error["message"])] for error in report["errors"])
            return output.getvalue().encode("utf-8-sig")
        total = len(report["errors"])
        pages = max(1, (total + size - 1) // size)
        page = min(page, pages)
        return {"valid": not total, "row_count": report["row_count"], "valid_rows": len(report["records"]),
                "error_count": total, "errors": report["errors"][(page - 1) * size:page * size],
                "page": page, "page_size": size, "total_pages": pages, "file_sha256": report["file_sha256"],
                "encoding": report["encoding"], "adapter": report["adapter"], "currency": report["currency"],
                "receipt": receipt, "expires_in": self.approvals.ttl if receipt else None}
