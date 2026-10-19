"""Retention removes only registered healthy files and preserves unknown or changed files."""
import shutil
from ledgerdesk.application.backup_policy import BackupPolicyService
from ledgerdesk.application.data_management import DataManagementService
from tests.support.workspace import WorkspaceTest


class BackupRetentionTests(WorkspaceTest):
    def test_one_healthy_backup_survives_and_unknown_files_are_preserved(self):
        manager = DataManagementService(self.store.path)
        backups = [manager.create_backup() for _ in range(3)]
        unknown = manager.backup_dir / "backup-20260101T000000Z-00000000000000000000000000000000.sqlite3"
        shutil.copyfile(manager.backup_dir / backups[0]["id"], unknown)
        policy = BackupPolicyService(self.store); policy.save({"retain_count": 1}, 0)
        result = policy.prune()
        self.assertEqual((len(result["removed"]), len(result["retained"])), (2, 1))
        self.assertTrue(unknown.exists())
        self.assertEqual(manager.verify_backup(result["retained"][0])["status"], "ok")

    def test_modified_registered_backup_is_skipped(self):
        manager = DataManagementService(self.store.path)
        first = manager.create_backup(); manager.create_backup()
        path = manager.backup_dir / first["id"]
        with path.open("ab") as output:
            output.write(b"changed")
        service = BackupPolicyService(self.store); service.save({"retain_count": 1}, 0)
        result = service.prune()
        self.assertIn(first["id"], result["skipped"])
        self.assertTrue(path.exists())
