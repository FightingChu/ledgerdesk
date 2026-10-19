"""Yield at most 100 rows per CSV chunk and release buffers after each yield."""
import csv
import io
from ..application.reports import safe_cell
from ..domain.report_profiles import COLUMNS
from .cells import cell

NUMERIC = {"expected", "actual", "difference", "sales", "refunds", "order_count", "payment_count", "source_count", "tolerance_cents", "rule_revision"}


def csv_chunks(rows, context, columns):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([COLUMNS[key] for key in columns])
    yield b"\xef\xbb\xbf" + output.getvalue().encode("utf-8")
    output.seek(0); output.truncate(0)
    count = 0
    for row in rows:
        values = [cell(key, row, context) for key in columns]
        writer.writerow([value if key in NUMERIC else safe_cell(value) for key, value in zip(columns, values)])
        count += 1
        if count % 100 == 0:
            yield output.getvalue().encode("utf-8")
            output.seek(0); output.truncate(0)
    if output.tell():
        yield output.getvalue().encode("utf-8")
