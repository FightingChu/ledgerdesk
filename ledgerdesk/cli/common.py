"""Shared JSON output, filters and exclusive report writing."""
import json
from pathlib import Path
from ..domain.errors import InputError
from ..domain.filters import ResultFilter


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def filter_arguments(parser):
    parser.add_argument("--group", default="all")
    parser.add_argument("--reason", default="all")
    parser.add_argument("--status", default="all")
    parser.add_argument("--search", default="")


def result_filter(args):
    return ResultFilter(args.group, args.reason, args.status, args.search)


def write_stream(destination, chunks):
    path = Path(destination).resolve()
    if path.exists():
        raise InputError("输出文件已存在，未覆盖", code="conflict")
    path.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with path.open("xb") as output:
            created = True
            for chunk in chunks:
                output.write(chunk)
    except BaseException:
        if created:
            path.unlink(missing_ok=True)
        raise
    finally:
        close = getattr(chunks, "close", None)
        if close:
            close()
    return {"path": str(path), "bytes": path.stat().st_size}
