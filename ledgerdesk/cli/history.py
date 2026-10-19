"""List runs or compare two immutable versions with bounded response size."""


def configure(commands):
    parser = commands.add_parser("history", help="核对历史及差异")
    parser.add_argument("batch_id"); parser.add_argument("--older"); parser.add_argument("--newer")
    parser.add_argument("--page", type=int, default=1)


def run(args, store):
    if args.older or args.newer:
        return store.compare_page(args.batch_id, args.older, args.newer, args.page)
    return {"history": store.history(args.batch_id)}
