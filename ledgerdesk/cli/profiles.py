"""Inspect available report columns and create immutable profile revisions."""
from ..application.reporting import ReportingService
from ..domain.report_profiles import COLUMNS


def configure(commands):
    parser = commands.add_parser("profiles", help="报告配置管理")
    sub = parser.add_subparsers(dest="profile_action", required=True)
    sub.add_parser("list"); sub.add_parser("columns")
    create = sub.add_parser("create"); create.add_argument("name"); create.add_argument("--columns", required=True, help="按顺序逗号分隔字段键")


def run(args, store):
    service = ReportingService(store)
    if args.profile_action == "columns":
        return {"columns": COLUMNS}
    if args.profile_action == "list":
        return {"profiles": service.profiles()}
    return service.create_profile(args.name, args.columns.split(","))
