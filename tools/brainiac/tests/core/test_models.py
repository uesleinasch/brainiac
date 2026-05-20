from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from brainiac.core.models import SM2, NoteFrontmatter


def _base_fm(**overrides):
    defaults = dict(
        id="2026-05-20-foo",
        type="semantic",
        created=datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc),
        last_access=datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc),
        access_count=0,
        strength=1.0,
    )
    defaults.update(overrides)
    return defaults


class TestNoteFrontmatter:
    def test_minimal_valid(self):
        fm = NoteFrontmatter(**_base_fm())
        assert fm.id == "2026-05-20-foo"
        assert fm.tags == []
        assert fm.links == []
        assert fm.sm2 is None
        assert fm.source == "manual"

    def test_id_pattern_enforced(self):
        with pytest.raises(ValidationError):
            NoteFrontmatter(**_base_fm(id="bad id with spaces"))
        with pytest.raises(ValidationError):
            NoteFrontmatter(**_base_fm(id="2026/05/20-foo"))

    def test_type_enum(self):
        for t in ("episodic", "semantic", "working"):
            NoteFrontmatter(**_base_fm(type=t))
        with pytest.raises(ValidationError):
            NoteFrontmatter(**_base_fm(type="invalid"))

    def test_strength_bounds(self):
        NoteFrontmatter(**_base_fm(strength=0.0))
        NoteFrontmatter(**_base_fm(strength=1.0))
        with pytest.raises(ValidationError):
            NoteFrontmatter(**_base_fm(strength=-0.1))
        with pytest.raises(ValidationError):
            NoteFrontmatter(**_base_fm(strength=1.1))

    def test_access_count_non_negative(self):
        with pytest.raises(ValidationError):
            NoteFrontmatter(**_base_fm(access_count=-1))

    def test_sm2_optional(self):
        fm = NoteFrontmatter(
            **_base_fm(sm2=SM2(ease=2.5, interval=1, next_review=date(2026, 5, 21)))
        )
        assert fm.sm2.ease == 2.5


class TestSM2:
    def test_defaults(self):
        sm2 = SM2(next_review=date(2026, 5, 21))
        assert sm2.ease == 2.5
        assert sm2.interval == 1


class TestSM2Reps:
    def test_reps_defaults_to_zero(self):
        sm2 = SM2(next_review=date(2026, 5, 21))
        assert sm2.reps == 0

    def test_reps_accepts_positive_int(self):
        sm2 = SM2(reps=3, next_review=date(2026, 5, 21))
        assert sm2.reps == 3

    def test_reps_rejects_negative(self):
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SM2(reps=-1, next_review=date(2026, 5, 21))
