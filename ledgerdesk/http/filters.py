"""Saved filter CRUD preserves optimistic revisions."""
from .response import Response
from ..application.presets import PresetService


def get(context, parts, query):
    if parts == ["api", "filters"]:
        return Response({"filters": PresetService(context.store).list()})


def post(context, parts, payload):
    service = PresetService(context.store)
    if parts == ["api", "filters"]:
        return Response(service.save(payload.get("name"), payload.get("payload"), payload.get("expected_revision", 0)))
    if parts == ["api", "filters", "delete"]:
        return Response(service.delete(payload.get("id"), payload.get("revision")))
