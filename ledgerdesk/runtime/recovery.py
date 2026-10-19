"""Recover only report paths owned by known interrupted jobs."""
import hashlib
import re
from .report_files import report_directory


def recover_reports(store, con):
    rows = con.execute("SELECT id,result FROM jobs WHERE kind='report' AND state='running'").fetchall()
    if not rows:
        return
    import json
    directory = report_directory(store)
    for row in rows:
        if not re.fullmatch(r"[0-9a-f]{32}", row["id"]):
            continue
        result = json.loads(row["result"]) if row["result"] else None
        if result and result.get("filename") in (row["id"] + ".csv", row["id"] + ".html"):
            target = directory / result["filename"]
            if target.is_file() and not target.is_symlink():
                digest = hashlib.sha256()
                with target.open("rb") as source:
                    for chunk in iter(lambda: source.read(65536), b""):
                        digest.update(chunk)
                if digest.hexdigest() == result.get("sha256"):
                    con.execute("UPDATE jobs SET state='succeeded',progress=total,phase='已恢复完成的报告' WHERE id=?", (row["id"],))
        staging = directory / (row["id"] + ".partial")
        if staging.is_file() and not staging.is_symlink():
            staging.unlink()
