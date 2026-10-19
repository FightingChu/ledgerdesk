"""Export a fixed batch audit view without opening the browser."""
from pathlib import Path
from .common import write_stream
from ..application.audit_export import AuditExportService


def configure(commands):
    parser = commands.add_parser("audit-export", help="导出批次操作记录")
    parser.add_argument("batch_id")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--format", choices=("csv", "json"), default="csv")
    parser.add_argument("--action", default="all")
    parser.add_argument("--until-id", type=int)


def run(args, store):
    chunks = AuditExportService(store).stream(args.batch_id, args.action, args.format, args.until_id)
    return write_stream(args.out, chunks)
