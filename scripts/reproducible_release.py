"""Build twice at a fixed timestamp and verify identical source archive bytes."""
from contextlib import redirect_stdout
import hashlib
import io
import os
from pathlib import Path
from build_release import main as build


def verify():
    previous = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = "1735689600"
    try:
        with redirect_stdout(io.StringIO()):
            build()
        import json
        root = Path(__file__).resolve().parent.parent
        manifest = json.loads((root / "dist/release.json").read_text())
        path = root / "dist" / manifest["archive"]
        first = path.read_bytes()
        with redirect_stdout(io.StringIO()):
            build()
        if first != path.read_bytes():
            raise ValueError("Source archive is not reproducible")
        return {"reproducible": True, "sha256": hashlib.sha256(first).hexdigest(), "files": manifest["files"]}
    finally:
        if previous is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = previous


if __name__ == "__main__":
    print(verify())
