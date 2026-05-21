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


def test_config_has_actr_decay_default(fake_brainiac):
    from brainiac.core.config import load_config
    cfg = load_config(fake_brainiac)
    assert cfg.actr_decay == 0.5


def test_config_has_actr_recall_hit_weight_default(fake_brainiac):
    from brainiac.core.config import load_config
    cfg = load_config(fake_brainiac)
    assert cfg.actr_recall_hit_weight == 0.3


def test_config_has_actr_link_in_weight_default(fake_brainiac):
    from brainiac.core.config import load_config
    cfg = load_config(fake_brainiac)
    assert cfg.actr_link_in_weight == 0.5


def test_config_reads_actr_fields_from_toml(fake_brainiac):
    from brainiac.core.config import load_config

    (fake_brainiac / "brainiac.toml").write_text(
        "actr_decay = 0.3\nactr_recall_hit_weight = 0.4\nactr_link_in_weight = 0.6\n",
        encoding="utf-8",
    )
    cfg = load_config(fake_brainiac)
    assert cfg.actr_decay == 0.3
    assert cfg.actr_recall_hit_weight == 0.4
    assert cfg.actr_link_in_weight == 0.6


def test_config_has_spreading_defaults(fake_brainiac):
    from brainiac.core.config import load_config
    cfg = load_config(fake_brainiac)
    assert cfg.spreading_max_hops == 3
    assert cfg.spreading_decay == 0.5
    assert cfg.spreading_epsilon == 0.01
    assert cfg.spreading_floor == 0.05


def test_config_reads_spreading_fields_from_toml(fake_brainiac):
    from brainiac.core.config import load_config

    (fake_brainiac / "brainiac.toml").write_text(
        "spreading_max_hops = 5\nspreading_decay = 0.3\n"
        "spreading_epsilon = 0.001\nspreading_floor = 0.1\n",
        encoding="utf-8",
    )
    cfg = load_config(fake_brainiac)
    assert cfg.spreading_max_hops == 5
    assert cfg.spreading_decay == 0.3
    assert cfg.spreading_epsilon == 0.001
    assert cfg.spreading_floor == 0.1
