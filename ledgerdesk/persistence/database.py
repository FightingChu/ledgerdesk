"""Database lifetime, transaction ownership and online backup."""
from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3
from ..domain.errors import InputError
from ..domain.values import identifier
from .migrations import SCHEMA_VERSION, check_version, create_v1, migrate


class Database:
    _check_version = staticmethod(check_version)
    _create_v1 = staticmethod(create_v1)

    def _migrate(self, con, version):
        migrate(con, version)

    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Inspect existing files read-only before changing schema or journal settings.
        if self.path.exists():
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as con:
                self._check_version(con)
        with self.connect() as con:
            # v2 -> v3 rebuilds the parent imports table. Disable FK enforcement
            # before BEGIN, then validate all references before the transaction commits.
            con.execute("PRAGMA foreign_keys=OFF")
            con.execute("BEGIN IMMEDIATE")
            version = self._check_version(con)
            if version == 0:
                self._create_v1(con)
            elif version < SCHEMA_VERSION:
                self.backup(self.path.with_name(
                    self.path.name + f".pre-v{version}-to-v{SCHEMA_VERSION}-{identifier()}.sqlite3"))
            for previous in range(version or 1, SCHEMA_VERSION):
                self._migrate(con, previous)
            if con.execute("PRAGMA foreign_key_check").fetchone():
                raise InputError("数据库外键检查失败，升级已回滚，请保留备份")
            if version < SCHEMA_VERSION:
                con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        with self.connect() as con:
            con.execute("PRAGMA journal_mode=WAL")

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=20)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            with con:
                yield con
        finally:
            con.close()

    def backup(self, destination):
        return self.backup_existing(self.path, destination)

    @classmethod
    def backup_existing(cls, path, destination):
        path = Path(path).resolve()
        if not path.is_file():
            raise InputError("备份源数据库不存在，请检查 --data-dir；未创建空数据库")
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=20)) as source:
            version = cls._check_version(source)
            if version == 0:
                raise InputError("备份源不是已初始化的 LedgerDesk 数据库")
            summary = {"schema_version": version,
                       "batches": source.execute("SELECT COUNT(*) FROM batches").fetchone()[0],
                       "entries": source.execute("SELECT COUNT(*) FROM entries").fetchone()[0]}
            cls._write_backup(source, path, destination)
            return summary

    @staticmethod
    def _write_backup(source, source_path, destination):
        destination = Path(destination).resolve()
        if destination == source_path or destination.exists():
            raise InputError("备份路径必须是尚不存在的新文件")
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Reserve the destination exclusively, so concurrent backups cannot
        # overwrite a file that appeared after the existence check.
        try:
            with destination.open("xb"):
                pass
        except FileExistsError:
            raise InputError("备份目标已存在，请选择新文件") from None
        try:
            with closing(sqlite3.connect(destination)) as target:
                source.backup(target)
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
