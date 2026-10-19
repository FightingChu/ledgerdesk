"""Evidence hashes, identifiers and bounded business text."""
from datetime import datetime, timezone
import hashlib
import json
import uuid
from .errors import InputError


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def identifier():
    return uuid.uuid4().hex


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def require_text(value, label, maximum):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise InputError(f"{label}须为 1～{maximum} 个字符")
    return value.strip()
