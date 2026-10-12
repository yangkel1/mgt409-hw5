"""Append-only audit trail at output/audit_trail.json.

The file is one JSON array. Each write loads the array, appends, and atomically
replaces the file, so earlier runs are never wiped. A file that can't be parsed
is renamed aside (never deleted) and a new array is started.
"""

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import AuditEvent

AUDIT_PATH = Path(__file__).resolve().parents[1] / "output" / "audit_trail.json"
MAX_FIELD_CHARS = 2000  # keep the trail readable; long tool results are truncated

_lock = threading.Lock()


def clip(value: Any, limit: int = MAX_FIELD_CHARS) -> Any:
    """Truncate long strings (and stringified objects) for the trail."""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, default=str)
        return value if len(text) <= limit else text[:limit] + "...[truncated]"
    text = value if isinstance(value, str) else str(value)
    return text if len(text) <= limit else text[:limit] + "...[truncated]"


def _load() -> list:
    if not AUDIT_PATH.exists():
        return []
    try:
        data = json.loads(AUDIT_PATH.read_text() or "[]")
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    aside = AUDIT_PATH.with_suffix(f".corrupt-{datetime.now():%Y%m%d%H%M%S}.json")
    AUDIT_PATH.rename(aside)
    return []


def append(event: AuditEvent) -> None:
    with _lock:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        events = _load()
        events.append(event.model_dump())
        tmp = AUDIT_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(events, indent=2, default=str))
        os.replace(tmp, AUDIT_PATH)


def read_all() -> list:
    with _lock:
        return _load()
