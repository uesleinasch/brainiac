from pathlib import Path

import pytest


def test_load_config_returns_defaults_when_no_toml(fake_brainiac):
    from brainiac.core.config import Config, load_config

    cfg = load_config(fake_brainiac)
    assert isinstance(cfg, Config)
    assert cfg.working_memory_limit == 9
    assert cfg.classifier_threshold == 0.3


def test_load_config_reads_from_brainiac_toml(fake_brainiac):
    from brainiac.core.config import load_config

    (fake_brainiac / "brainiac.toml").write_text(
        'working_memory_limit = 5\nclassifier_threshold = 0.5\n',
        encoding="utf-8",
    )
    cfg = load_config(fake_brainiac)
    assert cfg.working_memory_limit == 5
    assert cfg.classifier_threshold == 0.5


def test_load_config_partial_overrides_keeps_defaults(fake_brainiac):
    from brainiac.core.config import load_config

    (fake_brainiac / "brainiac.toml").write_text(
        'working_memory_limit = 12\n',
        encoding="utf-8",
    )
    cfg = load_config(fake_brainiac)
    assert cfg.working_memory_limit == 12
    assert cfg.classifier_threshold == 0.3  # default preserved


def test_load_config_rejects_unknown_keys(fake_brainiac):
    from brainiac.core.config import load_config

    (fake_brainiac / "brainiac.toml").write_text(
        'working_memory_limit = 9\nunknown_key = "x"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown_key"):
        load_config(fake_brainiac)


def test_load_config_rejects_invalid_types(fake_brainiac):
    from brainiac.core.config import load_config

    (fake_brainiac / "brainiac.toml").write_text(
        'working_memory_limit = "nine"\n',
        encoding="utf-8",
    )
    with pytest.raises(TypeError):
        load_config(fake_brainiac)
