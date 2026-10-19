"""Durable queue controls and downloads constrained to a completed job's own report."""
from .response import Response
from .parameters import paging, single
from ..application.jobs import JobService
from ..domain.errors import InputError
from ..runtime.report_files import report_directory


def get(context, parts, query):
    service = JobService(context.store)
    if parts == ["api", "jobs"]:
        return Response(service.list(*paging(query), state=single(query, "state", "all")))
    if len(parts) >= 3 and parts[:2] == ["api", "jobs"]:
        job = service.get(parts[2])
        if len(parts) == 3:
            return Response(job)
        if len(parts) == 4 and parts[3] == "manifest":
            if job["kind"] != "report" or job["state"] != "succeeded":
                raise InputError("任务尚无报告说明", code="not_found")
            import json
            return Response(json.dumps(job["result"], ensure_ascii=False, indent=2).encode(),
                headers={"Content-Disposition": 'attachment; filename="ledgerdesk-report-manifest.json"'})
        if len(parts) == 4 and parts[3] == "download":
            result = job["result"] or {}
            expected = job["id"] + "." + job["payload"].get("format", "csv")
            if job["kind"] != "report" or job["state"] != "succeeded" or result.get("filename") != expected:
                raise InputError("任务尚无可下载的报告", code="not_found")
            path = report_directory(context.store) / expected
            if path.is_symlink() or not path.is_file():
                raise InputError("报告文件不存在", code="not_found")
            def chunks():
                with path.open("rb") as source:
                    for chunk in iter(lambda: source.read(65536), b""):
                        yield chunk
            mime = "text/csv; charset=utf-8" if expected.endswith(".csv") else "text/html; charset=utf-8"
            return Response(chunks(), content_type=mime, headers={"Content-Disposition": f'attachment; filename="{expected}"'}, stream=True)


def post(context, parts, payload):
    service = JobService(context.store)
    if parts == ["api", "jobs"]:
        return Response(service.enqueue(payload.get("kind"), payload.get("batch_id"), payload.get("payload"), payload.get("dedupe_key")))
    if parts == ["api", "jobs", "queue"]:
        return Response(service.enqueue_batch(payload.get("batch_ids"), payload.get("request_id")))
    if len(parts) == 4 and parts[:2] == ["api", "jobs"]:
        if parts[3] == "cancel":
            return Response(service.cancel(parts[2]))
        if parts[3] == "retry":
            return Response(service.retry(parts[2]))
