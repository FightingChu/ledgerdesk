"""Managed local backups and recovery exclusively into a new workspace."""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import shutil
import threading
import uuid
from ..domain.errors import InputError
from ..persistence.database import Database
from ..persistence.diagnostics import inspect_database

BACKUP_NAME = re.compile(r"backup-\d{8}T\d{6}Z-[0-9a-f]{32}\.sqlite3")
WORKSPACE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")


def healthy(path):
    report = inspect_database(path)
    if report["status"] != "ok":
        raise InputError("数据库不存在、损坏、不属于 LedgerDesk 或版本不受支持；请先执行诊断", code="invalid_database")
    return report


def restore_database(source, destination_dir):
    """Copy via SQLite backup, preserve the source version, and refuse any existing directory."""
    source = Path(source).resolve()
    destination = Path(destination_dir).resolve()
    if destination.exists():
        raise InputError("恢复目标必须是尚不存在的新数据目录，不会覆盖已有目录", code="conflict")
    healthy(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.mkdir()
    except FileExistsError:
        raise InputError("恢复目标目录已存在，请换一个新名称", code="conflict") from None
    target = destination / "ledgerdesk.sqlite3"
    staging = destination / (".restore-" + uuid.uuid4().hex + ".sqlite3")
    created_target = False
    try:
        Database.backup_existing(source, staging)
        report = healthy(staging)
        try:
            # A hard link publishes the validated file without replacing a path
            # another process created while the copy was running.
            os.link(staging, target)
            created_target = True
        except FileExistsError:
            raise InputError("恢复目标文件已出现，未覆盖；请使用另一个新目录", code="conflict") from None
        except OSError:
            # Some filesystems do not support hard links. Exclusive creation
            # still guarantees the fallback cannot overwrite an existing file.
            with target.open("xb") as output:
                created_target = True
                with staging.open("rb") as input_file:
                    shutil.copyfileobj(input_file, output)
                output.flush()
                os.fsync(output.fileno())
        staging.unlink()
    except BaseException:
        # Only remove the exclusive output we created; never recursively remove a workspace.
        if staging.is_file():
            staging.unlink()
        if created_target and target.is_file():
            target.unlink()
        try:
            destination.rmdir()
        except OSError:
            pass
        raise
    return {"restored": True, "data_dir": str(destination), "schema_version": report["schema_version"],
            "counts": report["counts"], "status": report["status"]}


class DataManagementService:
    def __init__(self, database_path):
        self.path = Path(database_path).resolve()
        self.backup_dir = self.path.parent / "backups"
        self.restore_dir = self.path.parent / "restored"
        self.lock = threading.RLock()

    def _directory(self, path, create=False):
        if path.is_symlink() or path.resolve() != path:
            raise InputError("数据管理目录不能是链接或重定向目录", code="invalid_path")
        if path.exists() and not path.is_dir():
            raise InputError("数据管理路径不是目录", code="invalid_path")
        if create:
            path.mkdir(exist_ok=True)
        return path

    def _backup(self, backup_id):
        if not isinstance(backup_id, str) or not BACKUP_NAME.fullmatch(backup_id):
            raise InputError("备份 ID 无效，请从列表选择", code="invalid_backup")
        directory = self._directory(self.backup_dir)
        file = directory / backup_id
        if file.is_symlink() or not file.is_file() or file.resolve().parent != directory:
            raise InputError("备份不存在或不是本机管理的文件", code="not_found")
        return file

    def list_backups(self):
        directory = self._directory(self.backup_dir)
        if not directory.exists():
            return []
        files = [file for file in directory.iterdir() if BACKUP_NAME.fullmatch(file.name)
                 and not file.is_symlink() and file.is_file() and file.resolve().parent == directory]
        result = []
        for file in sorted(files, key=lambda file: (file.stat().st_mtime_ns, file.name), reverse=True)[:100]:
            stat = file.stat()
            result.append({"id": file.name, "bytes": stat.st_size,
                           "created_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds")})
        return result

    def create_backup(self):
        with self.lock:
            healthy(self.path)
            directory = self._directory(self.backup_dir, create=True)
            name = "backup-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex + ".sqlite3"
            summary = Database.backup_existing(self.path, directory / name)
            checked = self.verify_backup(name)
            if checked["status"] != "ok":
                raise InputError("备份已生成但校验失败，请检查磁盘与诊断信息", code="invalid_database")
            return {"id": name, **summary, "status": checked["status"], "sha256": checked["sha256"]}

    def verify_backup(self, backup_id):
        with self.lock:
            file = self._backup(backup_id)
            report = inspect_database(file)
            digest = hashlib.sha256()
            with file.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            return {"id": backup_id, **report, "sha256": digest.hexdigest()}

    def restore_backup(self, backup_id, workspace_name):
        if not isinstance(workspace_name, str) or not WORKSPACE_NAME.fullmatch(workspace_name):
            raise InputError("新目录名称须为 1～64 个英文字母、数字、下划线或短横线，以字母或数字开头", code="invalid_path")
        # Names reserved by Windows are invalid even when running on another OS.
        if workspace_name.upper() in {"CON", "PRN", "AUX", "NUL", *["COM" + str(i) for i in range(1, 10)], *["LPT" + str(i) for i in range(1, 10)]}:
            raise InputError("此目录名称被系统保留，请更换", code="invalid_path")
        with self.lock:
            source = self._backup(backup_id)
            healthy(source)
            parent = self._directory(self.restore_dir, create=True)
            return restore_database(source, parent / workspace_name)
