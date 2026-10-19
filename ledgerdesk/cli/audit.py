"""Stable audit pages for terminal workflows."""


def configure(commands):
    parser = commands.add_parser("audit", help="批次操作记录")
    parser.add_argument("batch_id"); parser.add_argument("--action", default="all")
    parser.add_argument("--page", type=int, default=1); parser.add_argument("--until-id", type=int)


def run(args, store):
    return store.audit_page(args.batch_id, page=args.page, action=args.action, until_id=args.until_id)
