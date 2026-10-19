"""Execute a fixed set of local use cases and recheck queued input identities."""
from ..domain.errors import InputError
from ..domain.filters import ResultFilter
from ..application.reporting import ReportingService
from ..application.data_management import DataManagementService
from .report_files import write_report


def execute(store, job, context):
    context.checkpoint()
    batch_id, payload = job["batch_id"], job["payload"]
    if batch_id is not None:
        with store.connect() as con:
            (store.require_editable if job["kind"] == "reconcile" else store.batch)(con, batch_id)
            if store.source_fingerprint(con, batch_id) != payload["input_identity"]:
                raise InputError("排队期间输入已变化，请提交新任务", code="stale_result")
    context.progress(0, 1, "执行" + job["kind"])
    if job["kind"] == "reconcile":
        from ..application.reconciliation import ReconciliationService
        return ReconciliationService(store).run(batch_id, payload["input_identity"])
    if job["kind"] == "backup":
        return DataManagementService(store.path).create_backup()
    metadata = {}
    chunks = ReportingService(store).stream(batch_id, ResultFilter(**payload["filters"]), payload["run_id"], payload["profile_id"], payload["format"], metadata)
    return write_report(store, job, chunks, context, metadata)
