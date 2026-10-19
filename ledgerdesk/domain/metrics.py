"""Integer projections for SQL aggregation without reading source arrays."""
from decimal import Decimal
from .money import money


def display_cents(value):
    return int(Decimal(str(value).replace(",", "")) * 100)


def metric_values(run_id, row):
    return (run_id, row["case_key"], row["channel"], *[display_cents(row[name]) for name in
            ("expected", "actual", "difference", "sales", "refunds")])


def format_totals(row):
    result = dict(row)
    for name in ("expected", "actual", "difference", "sales", "refunds"):
        result[name] = money(result.get(name, 0) or 0)
    return result
