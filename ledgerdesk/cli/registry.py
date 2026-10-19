"""Register actual CLI commands and select one shared service implementation."""
from . import batches, imports, reconcile, reports, rules, statistics, jobs, audit, evidence, history, maintenance, reviews, profiles, presets, audit_export
from .common import emit
from ..domain.errors import InputError

COMMANDS = {"batches": batches, "imports": imports, "reconcile": reconcile, "report": reports,
            "rules": rules, "stats": statistics, "jobs": jobs, "audit": audit, "evidence": evidence,
            "history": history, "maintenance": maintenance, "reviews": reviews, "profiles": profiles, "filters": presets, "audit-export": audit_export}


def configure(parser):
    commands = parser.add_subparsers(dest="command")
    for module in COMMANDS.values():
        module.configure(commands)


def execute(args, database_path):
    from ..store import Store
    create = args.command == "batches" and args.batch_action == "create"
    if not database_path.is_file() and not create:
        raise InputError("数据目录中尚无数据库，请先创建批次")
    store = Store(database_path)
    emit(COMMANDS[args.command].run(args, store))
