"""Backup policy defaults are opt-in and version conflicts preserve the old setting."""
from ledgerdesk.application.backup_policy import BackupPolicyService
from ledgerdesk.domain.errors import InputError
from tests.support.workspace import WorkspaceTest


class BackupPolicyTests(WorkspaceTest):
    def test_startup_default_creates_no_backup(self):
        service = BackupPolicyService(self.store)
        self.assertFalse(service.get()["payload"]["startup"])
        self.assertIsNone(service.startup())
        self.assertFalse((self.root / "backups").exists())

    def test_save_conflict_and_invalid_policy(self):
        service = BackupPolicyService(self.store)
        saved = service.save({"startup": False, "retain_count": 2, "max_age_days": 0}, 0)
        self.assertEqual(saved["revision"], 1)
        for payload in ({"retain_count": 0}, {"startup": "yes"}, {"max_age_days": -1}, {"unknown": 1}):
            with self.subTest(payload=payload), self.assertRaises(InputError):
                service.save(payload, 1)
        with self.assertRaises(InputError):
            service.save(saved["payload"], 0)

    def test_enabled_startup_creates_a_verified_registered_restore_point(self):
        service = BackupPolicyService(self.store)
        service.save({"startup": True}, 0)
        result = service.startup()
        self.assertEqual(result["backup"]["status"], "ok")
        with self.store.connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM managed_backups").fetchone()[0], 1)
