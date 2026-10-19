"""Create immutable rule revisions and explicitly bind a batch."""
from ..application.rules import RuleService


def configure(commands):
    parser = commands.add_parser("rules", help="规则版本管理")
    sub = parser.add_subparsers(dest="rule_action", required=True)
    sub.add_parser("list")
    create = sub.add_parser("create")
    create.add_argument("name"); create.add_argument("--tolerance-cents", type=int, required=True)
    select = sub.add_parser("select")
    select.add_argument("batch_id"); select.add_argument("rule_id", help="使用 default 恢复默认精确核对")


def run(args, store):
    service = RuleService(store)
    if args.rule_action == "list":
        return {"rules": service.list()}
    if args.rule_action == "create":
        return service.create(args.name, args.tolerance_cents)
    return service.select(args.batch_id, None if args.rule_id == "default" else args.rule_id)
