"""Version-required single and batch review commands."""
import json
from pathlib import Path


def configure(commands):
    parser = commands.add_parser("reviews", help="带运行和处理版本的人工处理")
    sub = parser.add_subparsers(dest="review_action", required=True)
    single = sub.add_parser("set")
    single.add_argument("batch_id"); single.add_argument("case_key")
    single.add_argument("--run-id", required=True); single.add_argument("--evidence", required=True)
    single.add_argument("--revision", type=int, required=True)
    single.add_argument("--status", choices=("pending", "in_progress", "resolved"), required=True)
    single.add_argument("--note", default="")
    bulk = sub.add_parser("bulk"); bulk.add_argument("batch_id"); bulk.add_argument("request", type=Path)


def run(args, store):
    if args.review_action == "set":
        return store.review(args.batch_id, args.case_key, args.evidence, args.status, args.note, args.run_id, args.revision)
    value = json.loads(args.request.read_text(encoding="utf-8-sig"))
    from ..domain.errors import InputError
    if not isinstance(value, dict):
        raise InputError("批量处理文件须为 JSON 对象")
    return store.bulk_review(args.batch_id, value.get("run_id"), value.get("items"), value.get("status"), value.get("note", ""))
