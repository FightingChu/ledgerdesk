"""Public compatibility facade for application workflows and SQLite repositories."""
import json
from .imports import parse
from .domain.errors import InputError
from .domain.money import money
from .domain.values import now, identifier, digest, require_text
from .domain.reconciliation import LABELS, REVIEW_LABELS, RECONCILIATION_VERSION
from .domain.mappings import normalize_aliases
from .domain.history import compare_results
from .persistence.database import Database
from .persistence.migrations import SCHEMA_VERSION
from .persistence.templates import TemplateRepository
from .persistence.runs import RunRepository
from .application.reconciliation import ReconciliationService
from .persistence.result_queries import ResultQueryRepository
from .domain.filters import ResultFilter
from .persistence.batches import BatchRepository
from .persistence.imports import ImportRepository
from .persistence.audit import AuditRepository
from .application.batches import BatchService
from .application.imports import ImportService
from .application.reviews import ReviewService


class Store(Database):
    normalize_aliases = staticmethod(normalize_aliases)

    def list_templates(self, side=None):
        return TemplateRepository(self).list(side)

    def save_template(self, name, side, mapping, channel_aliases=None):
        return TemplateRepository(self).save(name, side, mapping, channel_aliases)

    def delete_template(self, template_id):
        return TemplateRepository(self).delete(template_id)

    def copy_template(self, template_id, name):
        return TemplateRepository(self).copy(template_id, name)

    def export_templates(self):
        return TemplateRepository(self).export()

    def import_templates(self, bundle):
        return TemplateRepository(self).import_bundle(bundle)

    @staticmethod
    def source_fingerprint(con, batch_id):
        return RunRepository.fingerprint(con, batch_id)

    def reconcile(self, batch_id):
        return ReconciliationService(self).run(batch_id)

    @staticmethod
    def batch(con, batch_id):
        return BatchRepository.get(con, batch_id)

    @classmethod
    def require_editable(cls, con, batch_id):
        return BatchRepository.require_editable(con, batch_id)

    def update_batch(self, batch_id, tags=None, archived=None):
        return BatchService(self).update(batch_id, tags, archived)

    @staticmethod
    def audit(con, batch_id, action, payload):
        return AuditRepository.append(con, batch_id, action, payload)

    def create_batch(self, name, description="", is_sample=False):
        return BatchService(self).create(name, description, is_sample)

    def list_batches(self):
        with self.connect() as con:
            return BatchRepository.list(con)

    @staticmethod
    def active_import(con, batch_id, import_id, side=None):
        return ImportRepository.active(con, batch_id, import_id, side)

    def import_backup(self):
        destination = self.path.with_name(self.path.name + f".before-import-{identifier()}.sqlite3")
        self.backup(destination)
        return destination.name

    def revoke_import(self, batch_id, import_id, reason):
        return ImportService(self).revoke(batch_id, import_id, reason)

    def import_file(self, batch_id, side, filename, content, mapping, replace_id=None, reason="", channel_aliases=None):
        return ImportService(self).add(batch_id, side, filename, content, mapping, replace_id, reason, channel_aliases)

    def detail(self, batch_id):
        with self.connect() as con:
            con.execute("BEGIN")
            batch = self.batch(con, batch_id)
            files = [dict(row) for row in con.execute("SELECT id,side,filename,file_sha256,row_count,created_at,currency_policy,is_active,revoked_at,revoked_reason,replaces_id,channel_aliases,adapter_id,adapter_version FROM imports WHERE batch_id=? ORDER BY rowid", (batch_id,))]
            latest = con.execute("SELECT * FROM runs WHERE batch_id=? ORDER BY rowid DESC LIMIT 1", (batch_id,)).fetchone()
            results = []
            if latest:
                for row in con.execute("""
                    SELECT r.payload,v.status,v.note,v.updated_at,v.revision FROM results r
                    LEFT JOIN reviews v ON v.batch_id=? AND v.case_key=r.case_key AND v.evidence_sha256=r.evidence_sha256
                    WHERE r.run_id=? ORDER BY r.rowid
                """, (batch_id, latest["id"])):
                    item = json.loads(row["payload"])
                    item.update(review_status=row["status"] or "pending", note=row["note"] or "", reviewed_at=row["updated_at"], review_revision=row["revision"] or 0)
                    results.append(item)
            # Compute stale state using the same source fingerprint as reconcile.
            stale = bool(latest and latest["input_sha256"] != self.source_fingerprint(con, batch_id))
            audit = [dict(row) for row in con.execute("SELECT action,payload,created_at FROM audit WHERE batch_id=? ORDER BY id DESC LIMIT 50", (batch_id,))]
            return {"batch": batch, "imports": files, "run": ({"id": latest["id"], "created_at": latest["created_at"],
                    "summary": json.loads(latest["summary"])} if latest else None),
                    "results": results, "stale": stale, "audit": audit}

    def overview(self, batch_id):
        with self.connect() as con:
            con.execute("BEGIN")
            batch = self.batch(con, batch_id)
            files = [dict(row) for row in con.execute("""SELECT id,side,filename,file_sha256,row_count,created_at,
                currency_policy,is_active,revoked_at,revoked_reason,replaces_id,channel_aliases,adapter_id,adapter_version
                FROM imports WHERE batch_id=? ORDER BY rowid""", (batch_id,))]
            run = ResultQueryRepository.resolve(con, batch_id, None)
            stale = bool(run and run["input_sha256"] != self.source_fingerprint(con, batch_id))
            history = [dict(row) for row in con.execute("SELECT id,created_at,summary FROM runs WHERE batch_id=? ORDER BY rowid DESC LIMIT 30", (batch_id,))]
            for row in history:
                row["summary"] = json.loads(row["summary"])
            audit = [dict(row) for row in con.execute("SELECT action,payload,created_at FROM audit WHERE batch_id=? ORDER BY id DESC LIMIT 50", (batch_id,))]
            return {"batch": batch, "imports": files, "history": history, "audit": audit, "stale": stale,
                    "run": {"id": run["id"], "created_at": run["created_at"], "summary": json.loads(run["summary"])} if run else None}

    def result_page(self, batch_id, filters=None, page=1, page_size=50, run_id=None, historical=False):
        ResultQueryRepository.validate_page(page, page_size)
        filters = filters or ResultFilter()
        with self.connect() as con:
            con.execute("BEGIN")
            run = ResultQueryRepository.resolve(con, batch_id, run_id, historical)
            read_only = historical or bool(self.batch(con, batch_id)["archived"])
            if run is None:
                return {"run_id": None, "items": [], "page": 1, "page_size": page_size, "total": 0,
                        "total_pages": 1, "stale": False, "read_only": read_only}
            selection = ResultQueryRepository.selection(batch_id, run["id"], filters, historical)
            total = ResultQueryRepository.count(con, selection)
            pages = max(1, (total + page_size - 1) // page_size)
            page = min(page, pages)
            items = list(ResultQueryRepository.summaries(con, selection, page_size, (page - 1) * page_size))
            stale = not historical and run["input_sha256"] != self.source_fingerprint(con, batch_id)
            return {"run_id": run["id"], "items": items, "page": page, "page_size": page_size,
                    "total": total, "total_pages": pages, "stale": stale, "read_only": read_only,
                    "created_at": run["created_at"], "summary": json.loads(run["summary"])}

    def case_detail(self, batch_id, case_key, run_id=None, historical=False):
        with self.connect() as con:
            con.execute("BEGIN")
            run = ResultQueryRepository.resolve(con, batch_id, run_id, historical)
            if run is None:
                raise InputError("请先执行核对", code="not_found")
            batch = self.batch(con, batch_id)
            stale = not historical and run["input_sha256"] != self.source_fingerprint(con, batch_id)
            return {"run_id": run["id"], "item": ResultQueryRepository.case(con, batch_id, run, case_key, historical),
                    "read_only": historical or bool(batch["archived"]), "stale": stale}

    def export_rows(self, batch_id, filters=None, run_id=None):
        with self.connect() as con:
            con.execute("BEGIN")
            run = ResultQueryRepository.resolve(con, batch_id, run_id)
            if run is None or run["input_sha256"] != self.source_fingerprint(con, batch_id):
                raise InputError("数据或核对版本已变化，请重新核对后导出", code="stale_result")
            selection = ResultQueryRepository.selection(batch_id, run["id"], filters or ResultFilter())
            yield from ResultQueryRepository.summaries(con, selection)

    def history(self, batch_id, limit=30):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise InputError("历史列表每次最多返回 100 项")
        with self.connect() as con:
            self.batch(con, batch_id)
            history = [dict(row) for row in con.execute(
                "SELECT id,created_at,summary,input_sha256 FROM runs WHERE batch_id=? ORDER BY rowid DESC LIMIT ?",
                (batch_id, limit))]
            for run in history:
                run["summary"] = json.loads(run["summary"])
            return history

    def run_detail(self, batch_id, run_id):
        with self.connect() as con:
            con.execute("BEGIN")
            self.batch(con, batch_id)
            run = RunRepository.get(con, batch_id, run_id)
            run["summary"] = json.loads(run["summary"])
            results = RunRepository.payloads(con, run_id)
            for result in results:
                snapshot = result.get("review_snapshot")
                result["review_status"] = snapshot["status"] if snapshot else "unknown"
                result["note"] = snapshot["note"] if snapshot else ""
            return {"run": run, "results": results, "read_only": True}

    def compare_runs(self, batch_id, older_id, newer_id):
        with self.connect() as con:
            con.execute("BEGIN")
            self.batch(con, batch_id)
            RunRepository.get(con, batch_id, older_id)
            RunRepository.get(con, batch_id, newer_id)
            result = compare_results(RunRepository.payloads(con, older_id), RunRepository.payloads(con, newer_id))
            return {"older_id": older_id, "newer_id": newer_id, **result}

    def compare_page(self, batch_id, older_id, newer_id, page=1, page_size=50):
        ResultQueryRepository.validate_page(page, page_size)
        with self.connect() as con:
            con.execute("BEGIN")
            RunRepository.get(con, batch_id, older_id)
            RunRepository.get(con, batch_id, newer_id)
            def summaries(run_id):
                selection = ResultQueryRepository.selection(batch_id, run_id, ResultFilter(), historical=True)
                return list(ResultQueryRepository.summaries(con, selection))
            result = compare_results(summaries(older_id), summaries(newer_id))
            items = [{"kind": "added", "after": row} for row in result["added"]]
            items += [{"kind": "removed", "before": row} for row in result["removed"]]
            items += [{"kind": "changed", **row} for row in result["changed"]]
            total = len(items)
            pages = max(1, (total + page_size - 1) // page_size)
            page = min(page, pages)
            return {"older_id": older_id, "newer_id": newer_id, "counts": result["counts"], "total": total,
                    "page": page, "page_size": page_size, "total_pages": pages,
                    "items": items[(page - 1) * page_size:page * page_size]}

    def review(self, batch_id, case_key, evidence_hash, status, note, run_id=None, expected_revision=None):
        return ReviewService(self).single(batch_id, case_key, evidence_hash, status, note, run_id, expected_revision)

    def bulk_review(self, batch_id, run_id, items, status, note):
        return ReviewService(self).bulk(batch_id, run_id, items, status, note)

    def audit_page(self, batch_id, page=1, page_size=25, action="all", until_id=None):
        return AuditRepository.page(self, batch_id, page, page_size, action, until_id)
