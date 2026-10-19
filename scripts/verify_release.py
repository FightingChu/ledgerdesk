"""Verify a source archive in an isolated directory without repository data."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent


def main():
    manifest = json.loads((ROOT / "dist/release.json").read_text(encoding="utf-8"))
    archive = ROOT / "dist" / manifest["archive"]
    if hashlib.sha256(archive.read_bytes()).hexdigest() != manifest["sha256"]:
        raise ValueError("Release digest does not match manifest")
    with tempfile.TemporaryDirectory(prefix="ledgerdesk-release-") as directory:
        with zipfile.ZipFile(archive) as source:
            for name in source.namelist():
                parts = Path(name).parts
                if not parts or parts[0] != "LedgerDesk" or ".." in parts or Path(name).is_absolute():
                    raise ValueError("Unexpected archive path")
                if {"data", "backups", "exports", ".git", "__pycache__"}.intersection(parts):
                    raise ValueError("Runtime data in source archive")
            source.extractall(directory)
        subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
                       cwd=Path(directory) / "LedgerDesk", check=True)
    print("Extracted source archive verified:", manifest["archive"])


if __name__ == "__main__":
    main()
