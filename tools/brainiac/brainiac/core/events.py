import json
from datetime import datetime, timezone
from pathlib import Path


def log_event(
    root: Path,
    note_id: str,
    action: str,
    detail: str | None = None,
) -> None:
    """Append one event to memoryTransfer/logs/events.jsonl."""
    logs_dir = root / "memoryTransfer" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "note_id": note_id,
        "action": action,
        "detail": detail,
    }
    with (logs_dir / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
