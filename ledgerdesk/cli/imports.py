"""Explicit standard CSV import and revoke commands."""
import base64
import json
from pathlib import Path
from ..imports import preview


def configure(commands):
    parser = commands.add_parser("imports", help="导入或撤销标准 CSV")
    sub = parser.add_subparsers(dest="import_action", required=True)
    add = sub.add_parser("add")
    add.add_argument("batch_id"); add.add_argument("side", choices=("orders", "payments")); add.add_argument("file", type=Path)
    add.add_argument("--mapping", type=Path); add.add_argument("--aliases", type=Path)
    add.add_argument("--replace-id"); add.add_argument("--reason", default="")
    revoke = sub.add_parser("revoke")
    revoke.add_argument("batch_id"); revoke.add_argument("import_id"); revoke.add_argument("reason")


def run(args, store):
    if args.import_action == "revoke":
        return store.revoke_import(args.batch_id, args.import_id, args.reason)
    from ..ingestion.reading import MAX_BYTES
    from ..domain.errors import InputError
    with args.file.open("rb") as source:
        raw = source.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise InputError("文件超过 5 MiB 上限")
    content = base64.b64encode(raw).decode()
    mapping = json.loads(args.mapping.read_text(encoding="utf-8-sig")) if args.mapping else preview(args.side, content)["mapping"]
    aliases = json.loads(args.aliases.read_text(encoding="utf-8-sig")) if args.aliases else None
    return store.import_file(args.batch_id, args.side, args.file.name, content, mapping,
                             replace_id=args.replace_id, reason=args.reason, channel_aliases=aliases)
