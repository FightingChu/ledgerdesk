"""List, create and archive local batches."""


def configure(commands):
    parser = commands.add_parser("batches", help="批次列表、创建、归档与恢复")
    sub = parser.add_subparsers(dest="batch_action", required=True)
    sub.add_parser("list")
    create = sub.add_parser("create")
    create.add_argument("name"); create.add_argument("--description", default="")
    for action in ("archive", "restore"):
        item = sub.add_parser(action); item.add_argument("batch_id")


def run(args, store):
    if args.batch_action == "list":
        return {"batches": store.list_batches()}
    if args.batch_action == "create":
        return {"batch_id": store.create_batch(args.name, args.description)}
    return store.update_batch(args.batch_id, archived=args.batch_action == "archive")
