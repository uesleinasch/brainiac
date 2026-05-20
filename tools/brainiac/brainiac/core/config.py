from __future__ import annotations

import tomllib
import typing
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass(frozen=True)
class Config:
    working_memory_limit: int = 9
    classifier_threshold: float = 0.3


def load_config(root: Path) -> Config:
    """Load brainiac.toml from root, falling back to defaults.

    Raises ValueError on unknown keys (typo protection).
    """
    cfg_path = root / "brainiac.toml"
    if not cfg_path.exists():
        return Config()

    with cfg_path.open("rb") as f:
        data = tomllib.load(f)

    allowed = {f.name for f in fields(Config)}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"Unknown config keys in brainiac.toml: {sorted(unknown)}")

    # Validate types against dataclass field annotations.
    # Use get_type_hints() to resolve string annotations (from __future__ annotations).
    hints = typing.get_type_hints(Config)
    for f in fields(Config):
        if f.name in data:
            expected = hints[f.name]
            if not isinstance(data[f.name], expected):
                raise TypeError(
                    f"brainiac.toml: '{f.name}' must be {expected.__name__}, "
                    f"got {type(data[f.name]).__name__}"
                )

    return Config(**data)
