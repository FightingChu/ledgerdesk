"""Known print CSS shared by standalone reports and their CSP hash."""
import base64
import hashlib
from pathlib import Path

PRINT_STYLE = (Path(__file__).resolve().parent.parent / "static/print.css").read_text(encoding="utf-8")
STYLE_HASH = base64.b64encode(hashlib.sha256(PRINT_STYLE.encode()).digest()).decode()
