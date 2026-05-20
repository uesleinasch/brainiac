import os
from pathlib import Path

TYPE_TO_DIR: dict[str, str] = {
    "working": "shortMemory",
    "episodic": "longMemory/episodic",
    "semantic": "semanticMemory",
}

_ROOT_MARKERS = ("shortMemory", "semanticMemory")


def find_root(start: Path | None = None) -> Path:
    """Locate the brainiac root.

    Priority: BRAINIAC_ROOT env var > walk up from `start` (or cwd) looking
    for dirs that contain both `shortMemory/` and `semanticMemory/`.
    """
    if env := os.environ.get("BRAINIAC_ROOT"):
        return Path(env).resolve()

    p = (start or Path.cwd()).resolve()
    while True:
        if all((p / m).is_dir() for m in _ROOT_MARKERS):
            return p
        if p.parent == p:
            raise FileNotFoundError(
                f"Brainiac root not found from {start or Path.cwd()}. "
                f"Set BRAINIAC_ROOT or run from inside the project."
            )
        p = p.parent


def note_dir(root: Path, note_type: str) -> Path:
    """Filesystem dir where notes of this type live."""
    return root / TYPE_TO_DIR[note_type]


def note_path(root: Path, note_id: str, note_type: str) -> Path:
    """Full path for a note with given id and type."""
    return note_dir(root, note_type) / f"{note_id}.md"


def index_db_path(root: Path) -> Path:
    """Path to the SQLite index file."""
    return root / "memoryTransfer" / "index.sqlite"
