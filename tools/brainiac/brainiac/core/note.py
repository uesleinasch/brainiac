from datetime import datetime, timezone
from pathlib import Path

import frontmatter

from brainiac.core.models import NoteFrontmatter


def parse_note(path: Path) -> tuple[NoteFrontmatter, str]:
    """Read a .md note. Returns (frontmatter, body)."""
    post = frontmatter.load(str(path))
    fm = NoteFrontmatter.model_validate(post.metadata)
    return fm, post.content


def write_note(path: Path, fm: NoteFrontmatter, body: str) -> None:
    """Write a .md note with frontmatter. Creates parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = fm.model_dump(mode="json", exclude_none=True)
    post = frontmatter.Post(body, **metadata)
    path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")


def new_note(
    note_id: str,
    note_type: str,
    *,
    tags: list[str] | None = None,
    links: list[str] | None = None,
    source: str = "manual",
) -> NoteFrontmatter:
    """Build a NoteFrontmatter with sensible defaults (timestamps=now, counters=0)."""
    now = datetime.now(timezone.utc)
    return NoteFrontmatter(
        id=note_id,
        type=note_type,  # type: ignore[arg-type]
        created=now,
        last_access=now,
        access_count=0,
        strength=1.0,
        tags=tags or [],
        links=links or [],
        source=source,  # type: ignore[arg-type]
    )
