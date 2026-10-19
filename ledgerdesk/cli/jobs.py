"""Queue controls and an exclusive worker for scripts or recovery."""
import json
from ..application.jobs import JobService
from ..runtime.worker import JobWorker
from ..domain.errors import InputError


def configure(commands):
    parser = commands.add_parser("jobs", help="本机任务队列")
    sub = parser.add_subparsers(dest="job_action", required=True)
    listing = sub.add_parser("list"); listing.add_argument("--state", default="all")
    for action in ("get", "cancel", "retry"):
        item = sub.add_parser(action); item.add_argument("job_id")
    submit = sub.add_parser("submit")
    submit.add_argument("kind", choices=("reconcile", "report", "backup")); submit.add_argument("--batch-id")
    submit.add_argument("--payload", default="{}"); submit.add_argument("--request-id")
    work = sub.add_parser("work"); work.add_argument("--once", action="store_true")


def run(args, store):
    service = JobService(store)
    if args.job_action == "list":
        return service.list(state=args.state)
    if args.job_action in ("get", "cancel", "retry"):
        return getattr(service, args.job_action)(args.job_id)
    if args.job_action == "submit":
        return service.enqueue(args.kind, args.batch_id, json.loads(args.payload), args.request_id)
    worker = JobWorker(store)
    if not worker.acquire():
        raise InputError("此工作空间已有任务执行器", code="job_conflict")
    count = 0
    try:
        while worker.run_once():
            count += 1
            if args.once:
                break
    finally:
        worker.close()
    return {"processed": count}
