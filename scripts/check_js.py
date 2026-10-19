"""Syntax-check exactly the JavaScript files reviewed into the source release."""
from pathlib import Path
import shutil
import subprocess
from build_release import RELEASE_FILES


def main():
    node = shutil.which("node")
    if node is None:
        raise SystemExit("Node.js is needed for this developer check, not for running LedgerDesk")
    root = Path(__file__).resolve().parent.parent
    files = [name for name in RELEASE_FILES if name.endswith(".js")]
    for name in files:
        subprocess.run([node, "--check", str(root / name)], check=True)
    print("JavaScript syntax passed:", len(files), "files")


if __name__ == "__main__":
    main()
