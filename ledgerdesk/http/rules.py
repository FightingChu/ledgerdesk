"""Rule revision management and per-batch selection."""
from .response import Response
from ..application.rules import RuleService
from ..persistence.rules import RuleRepository


def get(context, parts, query):
    service = RuleService(context.store)
    if parts == ["api", "rules"]:
        return Response({"rules": service.list(), "default": RuleRepository.get(None, None).snapshot()})
    if len(parts) == 4 and parts[:2] == ["api", "batches"] and parts[3] == "rule":
        with context.store.connect() as con:
            return Response(RuleRepository.selected(con, parts[2]).snapshot())


def post(context, parts, payload):
    service = RuleService(context.store)
    if parts == ["api", "rules"]:
        return Response(service.create(payload.get("name"), payload.get("tolerance_cents")))
    if len(parts) == 4 and parts[:2] == ["api", "batches"] and parts[3] == "rule":
        return Response(service.select(parts[2], payload.get("rule_id")))
