"""Named filter management with explicit optimistic revisions."""
import json
from ..application.presets import PresetService


def configure(commands):
    parser = commands.add_parser("filters", help="常用筛选管理")
    sub = parser.add_subparsers(dest="filter_action", required=True)
    sub.add_parser("list")
    save = sub.add_parser("save"); save.add_argument("name"); save.add_argument("payload"); save.add_argument("--revision", type=int, default=0)
    delete = sub.add_parser("delete"); delete.add_argument("id"); delete.add_argument("--revision", type=int, required=True)


def run(args, store):
    service = PresetService(store)
    if args.filter_action == "list":
        return {"filters": service.list()}
    if args.filter_action == "save":
        return service.save(args.name, json.loads(args.payload), args.revision)
    return service.delete(args.id, args.revision)
