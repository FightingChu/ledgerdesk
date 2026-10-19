"""Explicit lifecycle transitions, including recovery after process interruption."""
from ..errors import InputError

STATES = ("queued", "running", "succeeded", "failed", "cancelled", "interrupted")
TERMINAL = {"succeeded", "failed", "cancelled", "interrupted"}
TRANSITIONS = {"queued": {"running", "cancelled"}, "running": TERMINAL,
               "failed": {"queued"}, "cancelled": {"queued"}, "interrupted": {"queued"}, "succeeded": set()}


def require_transition(before, after):
    if after not in TRANSITIONS.get(before, set()):
        raise InputError("任务状态已变化，请刷新后操作", code="job_conflict")
