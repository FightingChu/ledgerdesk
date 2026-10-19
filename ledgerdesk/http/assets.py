"""Explicit public asset list for the expanded workbench."""
from pathlib import Path
from .response import Response

ROOT = Path(__file__).resolve().parent.parent / "static"
ASSETS = {"workbench.js", "rules.js", "reports.js", "tasks.js", "evidence.js", "presets.js", "backup-policy.js",
          "workspace.css", "tasks.css", "report-editor.css", "operations.css", "print.css"}


def get(context, parts, query):
    if len(parts) == 1 and parts[0] in ASSETS:
        name = parts[0]
        mime = "text/css; charset=utf-8" if name.endswith(".css") else "text/javascript; charset=utf-8"
        return Response((ROOT / name).read_bytes(), content_type=mime)
