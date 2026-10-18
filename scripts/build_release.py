"""Create a source release without databases, local history or test caches."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent.parent
EXCLUDED = {".git", "__pycache__", ".venv", ".pytest_cache", "data", "backups", "exports", "dist", "restored-data"}
SUFFIXES = {".py", ".js", ".css", ".html", ".csv", ".md", ".cmd", ".toml"}


def main():
    selected = []
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT)
        if not path.is_file() or EXCLUDED.intersection(relative.parts):
            continue
        if path.suffix in SUFFIXES or path.name == ".gitignore":
            selected.append(path)
    out = ROOT/"dist"
    out.mkdir(exist_ok=True)
    archive = out/"LedgerDesk-0.1.0.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        for path in selected:
            name = "LedgerDesk/"+path.relative_to(ROOT).as_posix()
            entry = zipfile.ZipInfo(name, date_time=(2026, 10, 18, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            zipped.writestr(entry, path.read_bytes())
    with zipfile.ZipFile(archive) as zipped:
        assert len(zipped.namelist()) == len(selected)
        assert zipped.testzip() is None
        for path in selected:
            name = "LedgerDesk/"+path.relative_to(ROOT).as_posix()
            assert zipped.read(name) == path.read_bytes()
        assert not any(set(Path(name).parts) & EXCLUDED for name in zipped.namelist())
    result = {"archive": archive.name, "files": len(selected), "bytes": archive.stat().st_size,
              "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "includes_runtime_data": False}
    (out/"release.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
