"""Workspace pages and filtered channel statistics."""
from .response import Response
from .parameters import paging, single, boolean
from ..application.statistics import StatisticsService
from ..domain.filters import ResultFilter


def get(context, parts, query):
    service = StatisticsService(context.store)
    if parts == ["api", "workspace"]:
        return Response(service.workspace(*paging(query), archived=boolean(query, "archived")))
    if len(parts) == 4 and parts[:2] == ["api", "batches"] and parts[3] == "statistics":
        page, size = paging(query)
        return Response(service.batch(parts[2], ResultFilter.from_query(query), single(query, "run_id"),
                                      boolean(query, "historical"), page, size))
