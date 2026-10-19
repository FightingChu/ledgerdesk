"""Read bounded source evidence from an explicit run."""
from ..application.evidence import EvidenceService


def configure(commands):
    parser = commands.add_parser("evidence", help="查看订单证据页")
    parser.add_argument("batch_id"); parser.add_argument("case_key")
    parser.add_argument("--run-id"); parser.add_argument("--historical", action="store_true")
    parser.add_argument("--kind", choices=("source", "duplicate"), default="source")
    parser.add_argument("--page", type=int, default=1); parser.add_argument("--page-size", type=int, default=25)


def run(args, store):
    return EvidenceService(store).read(args.batch_id, args.case_key, args.run_id, args.historical, args.kind, args.page, args.page_size)
