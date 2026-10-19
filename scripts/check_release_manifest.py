"""Verify the public allowlist, archive bytes and known private-file exclusions."""
from pathlib import Path
import re
import subprocess
import zipfile
from build_release import ROOT, RELEASE_FILES

PRIVATE = {"HANDOFF.md", "docs/VALIDATION.md", "config.local.json"}


def inspect(files, root):
    errors = []
    for name in files:
        if name in PRIVATE or set(Path(name).parts) & {"data", "backups", "exports", "dist", ".git", "__pycache__"}:
            errors.append(name + ": private/runtime path")
            continue
        data = (root / name).read_bytes()
        text = data.decode("utf-8-sig")
        if re.search(r"[A-Za-z]:[\\/](?:Users|Desktop)[\\/]", text):
            errors.append(name + ": machine-specific path")
        if re.search(r"-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----", text):
            errors.append(name + ": private key marker")
    return errors


def main():
    if len(RELEASE_FILES) != len(set(RELEASE_FILES)):
        raise SystemExit("Duplicate release entries")
    errors = inspect(RELEASE_FILES, ROOT)
    if (ROOT / ".git").exists():
        tracked = set(subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines())
        if tracked != set(RELEASE_FILES):
            errors.append("Tracked files differ from the reviewed release manifest")
    if errors:
        raise SystemExit("\n".join(errors))
    print("Reviewed source manifest passed:", len(RELEASE_FILES), "files")


if __name__ == "__main__":
    main()
