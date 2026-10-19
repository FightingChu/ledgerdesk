"""Only explicitly registered, verified backups are eligible for retention deletion."""
from ..domain.values import now


class BackupRegistry:
    @staticmethod
    def register(con, backup_id, sha256):
        con.execute("INSERT INTO managed_backups VALUES(?,?,?)", (backup_id, sha256, now()))

    @staticmethod
    def list(con):
        return [dict(row) for row in con.execute("SELECT * FROM managed_backups ORDER BY created_at DESC,rowid DESC")]
