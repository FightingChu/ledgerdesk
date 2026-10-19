"""Opt-in backup policy and explicit retention execution."""
from .response import Response
from ..application.backup_policy import BackupPolicyService


def get(context, parts, query):
    if parts == ["api", "backup-policy"]:
        return Response(BackupPolicyService(context.store).get())


def post(context, parts, payload):
    if parts == ["api", "backup-policy"]:
        return Response(BackupPolicyService(context.store).save(payload.get("payload"), payload.get("expected_revision")))
    if parts == ["api", "backup-policy", "prune"]:
        return Response(BackupPolicyService(context.store).prune())
