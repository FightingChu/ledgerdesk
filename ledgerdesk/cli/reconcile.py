"""Synchronous, transactional reconciliation command."""


def configure(commands):
    parser = commands.add_parser("reconcile", help="核对指定批次")
    parser.add_argument("batch_id")


def run(args, store):
    return store.reconcile(args.batch_id)
