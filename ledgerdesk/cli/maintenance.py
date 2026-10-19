"""Backup policy and conservative retention controls."""
import json
from ..application.backup_policy import BackupPolicyService
from ..application.data_management import DataManagementService


def configure(commands):
    parser = commands.add_parser("maintenance", help="备份策略与维护")
    sub = parser.add_subparsers(dest="maintenance_action", required=True)
    for name in ("policy", "backup", "prune"):
        sub.add_parser(name)
    setting = sub.add_parser("set-policy")
    setting.add_argument("payload"); setting.add_argument("--revision", type=int, required=True)


def run(args, store):
    service = BackupPolicyService(store)
    if args.maintenance_action == "policy":
        return service.get()
    if args.maintenance_action == "set-policy":
        return service.save(json.loads(args.payload), args.revision)
    if args.maintenance_action == "prune":
        return service.prune()
    return DataManagementService(store.path).create_backup()
