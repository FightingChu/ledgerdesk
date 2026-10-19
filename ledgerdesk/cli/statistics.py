"""Workspace or run-scoped channel statistics."""
from ..application.statistics import StatisticsService
from .common import filter_arguments, result_filter


def configure(commands):
    parser = commands.add_parser("stats", help="查看批次渠道统计或工作台")
    parser.add_argument("batch_id", nargs="?")
    parser.add_argument("--run-id"); parser.add_argument("--historical", action="store_true")
    parser.add_argument("--page", type=int, default=1); parser.add_argument("--page-size", type=int, default=25)
    filter_arguments(parser)


def run(args, store):
    service = StatisticsService(store)
    if not args.batch_id:
        return service.workspace(args.page, args.page_size)
    return service.batch(args.batch_id, result_filter(args), args.run_id, args.historical, args.page, args.page_size)
