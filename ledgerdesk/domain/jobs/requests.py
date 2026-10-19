"""Validate executable job kinds and reject arbitrary filesystem or command inputs."""
from dataclasses import asdict
from ..errors import InputError
from ..filters import ResultFilter
from ..values import require_text

KINDS = ("reconcile", "report", "backup")


def normalize(kind, batch_id, payload):
    if not isinstance(kind, str) or kind not in KINDS or not isinstance(payload, dict):
        raise InputError("任务类型或参数无效", code="invalid_job")
    if kind == "backup":
        if batch_id is not None or payload:
            raise InputError("备份任务不接受批次或自定义路径", code="invalid_job")
        return {}
    require_text(batch_id, "批次", 64)
    if kind == "reconcile":
        if payload:
            raise InputError("核对任务不接受额外参数", code="invalid_job")
        return {}
    if set(payload) - {"filters", "run_id", "profile_id", "format"}:
        raise InputError("报告任务包含未知参数", code="invalid_job")
    filters = payload.get("filters", {})
    if not isinstance(filters, dict) or set(filters) - {"group", "reason", "status", "q"}:
        raise InputError("任务筛选无效", code="invalid_filter")
    format = payload.get("format", "csv")
    if format not in ("csv", "html"):
        raise InputError("任务报告格式无效", code="invalid_report")
    return {"filters": asdict(ResultFilter(**filters)), "run_id": payload.get("run_id"),
            "profile_id": payload.get("profile_id"), "format": format}
