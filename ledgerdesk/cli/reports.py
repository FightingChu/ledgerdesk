"""Stream reports and manage immutable report profiles from the command line."""
from pathlib import Path
from .common import filter_arguments, result_filter, write_stream
from ..application.reporting import ReportingService


def configure(commands):
    parser = commands.add_parser("report", help="生成 CSV 或 HTML 报告")
    parser.add_argument("batch_id"); parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--format", choices=("csv", "html"), default="csv")
    parser.add_argument("--run-id"); parser.add_argument("--profile-id")
    parser.add_argument("--metadata-out", type=Path, help="把同次读快照的报告说明写入新 JSON 文件")
    filter_arguments(parser)


def run(args, store):
    import json
    from ..domain.errors import InputError
    if args.metadata_out and (args.metadata_out.exists() or args.metadata_out.resolve() == args.out.resolve()):
        raise InputError("报告说明输出须为不同的新文件", code="conflict")
    metadata = {}
    chunks = ReportingService(store).stream(args.batch_id, result_filter(args), args.run_id, args.profile_id, args.format, metadata)
    result = write_stream(args.out, chunks)
    if args.metadata_out:
        write_stream(args.metadata_out, iter([(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode()]))
        result["metadata_path"] = str(args.metadata_out.resolve())
    return result
