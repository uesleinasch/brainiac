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
