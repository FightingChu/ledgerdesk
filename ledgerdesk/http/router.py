"""Dispatch bounded feature adapters before the preserved legacy interfaces."""
from urllib.parse import urlsplit, parse_qs
from . import rules, statistics, evidence, reports, filters, preferences, jobs, assets

ROUTES = (assets, rules, statistics, evidence, reports, filters, preferences, jobs, assets)


class FeatureRouter:
    def __init__(self, context):
        self.context = context

    def get(self, path):
        parsed = urlsplit(path)
        parts = parsed.path.strip("/").split("/")
        query = parse_qs(parsed.query, keep_blank_values=True)
        for route in ROUTES:
            result = route.get(self.context, parts, query)
            if result is not None:
                return result

    def post(self, path, payload):
        parts = urlsplit(path).path.strip("/").split("/")
        for route in ROUTES:
            method = getattr(route, "post", None)
            result = method(self.context, parts, payload) if method else None
            if result is not None:
                return result
