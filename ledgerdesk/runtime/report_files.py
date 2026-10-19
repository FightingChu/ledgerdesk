"""Publish generated reports without overwriting existing files or accepting user paths."""
import os
import json
import hashlib
from pathlib import Path
from ..domain.errors import InputError


def report_directory(store):
    directory = store.path.parent / "exports"
    if directory.is_symlink() or directory.resolve() != directory:
        raise InputError("报告目录不能是链接", code="invalid_path")
    directory.mkdir(exist_ok=True)
    return directory


def write_report(store, job, chunks, context, metadata=None):
    directory = report_directory(store)
    suffix = job["payload"]["format"]
    target = directory / (job["id"] + "." + suffix)
    staging = directory / (job["id"] + ".partial")
    if target.exists() or staging.exists():
        raise InputError("任务报告文件已存在，请检查后提交新任务", code="conflict")
    created = False
    owned_target = False
    published = False
    digest = hashlib.sha256()
    try:
        with staging.open("xb") as output:
            created = True
            for chunk in chunks:
                context.checkpoint()
                output.write(chunk)
                digest.update(chunk)
            output.flush(); os.fsync(output.fileno())
        context.checkpoint()
        result = {"filename": target.name, "bytes": staging.stat().st_size, "sha256": digest.hexdigest(), "metadata": metadata or {}}
        with store.connect() as con:
            con.execute("UPDATE jobs SET result=?,phase='发布报告' WHERE id=? AND state='running'", (json.dumps(result), job["id"]))
        try:
            os.link(staging, target)
            owned_target = True
        except FileExistsError:
            raise InputError("报告目标已出现，未覆盖", code="conflict") from None
        except OSError:
            with target.open("xb") as output:
                owned_target = True
                with staging.open("rb") as source:
                    import shutil
                    shutil.copyfileobj(source, output)
                output.flush(); os.fsync(output.fileno())
        published = True
        staging.unlink()
        return result
    finally:
        close = getattr(chunks, "close", None)
        if close:
            close()
        if owned_target and not published and target.exists():
            target.unlink()
        if created and staging.exists():
            staging.unlink()
