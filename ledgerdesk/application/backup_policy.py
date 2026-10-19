"""Verified restore points survive retention; unknown files are never removed."""
from datetime import datetime, timezone
from ..domain.backup_policy import BackupPolicy, validate_policy
from ..persistence.preferences import PreferenceRepository
from ..persistence.backup_registry import BackupRegistry
from .data_management import DataManagementService


class BackupPolicyService:
    def __init__(self, store):
        self.store = store
        self.manager = DataManagementService(store.path)

    def get(self):
        with self.store.connect() as con:
            return PreferenceRepository.get(con, "backup_policy", BackupPolicy().payload())

    def save(self, payload, revision):
        policy = validate_policy(payload)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            return PreferenceRepository.save(con, "backup_policy", policy.payload(), revision)

    def prune(self):
        removed, retained, skipped = [], [], []
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            policy = validate_policy(PreferenceRepository.get(con, "backup_policy", BackupPolicy().payload())["payload"])
            registered = BackupRegistry.list(con)
            healthy = []
            for row in registered:
                try:
                    report = self.manager.verify_backup(row["id"])
                    if report["status"] == "ok" and report["sha256"] == row["sha256"]:
                        healthy.append(row)
                    else:
                        skipped.append(row["id"])
                except (OSError, ValueError):
                    skipped.append(row["id"])
            current_time = datetime.now(timezone.utc)
            for index, row in enumerate(healthy):
                age = (current_time - datetime.fromisoformat(row["created_at"])).total_seconds() / 86400
                expired = bool(policy.max_age_days and age > policy.max_age_days)
                if index == 0 or index < policy.retain_count and not expired:
                    retained.append(row["id"])
                    continue
                # This exact registered path has just passed integrity and hash checks.
                path = self.manager._backup(row["id"])
                path.unlink()
                con.execute("DELETE FROM managed_backups WHERE id=?", (row["id"],))
                removed.append(row["id"])
        return {"removed": removed, "retained": retained, "skipped": skipped}

    def startup(self):
        if not validate_policy(self.get()["payload"]).startup:
            return None
        backup = self.manager.create_backup()
        return {"backup": backup, "retention": self.prune()}
