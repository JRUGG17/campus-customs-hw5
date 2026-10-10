"""Append-only audit trail: output/audit_trail.json.

Every agent loop step is appended as one entry. The file is read, extended and written back
atomically, never recreated, so earlier runs are never wiped. A file that can't be parsed is
moved aside (not deleted) before a new one is started.
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

HW_DIR = Path(__file__).resolve().parent.parent
AUDIT_PATH = Path(os.getenv("AUDIT_PATH", HW_DIR / "output" / "audit_trail.json"))
_lock = asyncio.Lock()


def short(value, limit: int = 700):
    """Trim long strings so one entry stays readable. Nothing secret is ever passed in here."""
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= limit else text[:limit] + f"... [{len(text) - limit} more chars]"


async def append(entry: dict) -> None:
    entry = {"timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry}
    async with _lock:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        entries: list = []
        if AUDIT_PATH.exists() and AUDIT_PATH.stat().st_size > 0:
            try:
                entries = json.loads(AUDIT_PATH.read_text())
                if not isinstance(entries, list):
                    raise ValueError("audit trail is not a JSON array")
            except (json.JSONDecodeError, ValueError):
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                AUDIT_PATH.rename(AUDIT_PATH.with_name(f"audit_trail.unreadable-{stamp}.json"))
                entries = []
        entries.append(entry)
        tmp = AUDIT_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(entries, indent=2, default=str))
        tmp.replace(AUDIT_PATH)
