import pytest


# --- happy-path tests, one per type ---

def test_classify_episodic_first_person_past():
    from brainiac.core.classifier import classify
    typ, conf = classify("Hoje fui ao escritório e decidimos pivotar o produto.")
    assert typ == "episodic"
    assert conf > 0


def test_classify_semantic_definition_form():
    from brainiac.core.classifier import classify
    typ, conf = classify("BM25 é uma função de ranking probabilística usada em FTS.")
    assert typ == "semantic"
    assert conf > 0


def test_classify_working_short_body():
    from brainiac.core.classifier import classify
    typ, conf = classify("ideia: redis como cache?", tags=["wip"])
    assert typ == "working"
    assert conf > 0


def test_classify_working_question_or_draft():
    from brainiac.core.classifier import classify
    typ, conf = classify("TODO: investigar latência. preciso pensar mais sobre isso depois.")
    assert typ == "working"


def test_classify_episodic_via_tag():
    from brainiac.core.classifier import classify
    typ, conf = classify("Reunião com cliente A.", tags=["reuniao"])
    assert typ == "episodic"


def test_classify_semantic_via_tag():
    from brainiac.core.classifier import classify
    typ, conf = classify("Termo descontextualizado.", tags=["conceito"])
    assert typ == "semantic"


# --- ambiguity ---

def test_classify_ambiguous_returns_none():
    from brainiac.core.classifier import classify
    typ, conf = classify("Frase neutra sem marcadores.")
    assert typ is None
    assert conf == 0.0


def test_classify_empty_body_returns_working():
    """Empty/very short body without any marker is treated as working draft."""
    from brainiac.core.classifier import classify
    typ, _ = classify("rascunho")
    assert typ == "working"


# --- threshold tunable ---

def test_classify_threshold_lower_makes_borderline_decisive():
    from brainiac.core.classifier import classify
    typ_strict, _ = classify("Hoje aprendi algo.", threshold=0.5)
    typ_loose, _ = classify("Hoje aprendi algo.", threshold=0.2)
    # "Hoje" hits 1 episodic marker (0.3 score) — strict (0.5) → None, loose (0.2) → episodic
    assert typ_strict is None
    assert typ_loose == "episodic"


# --- return type ---

def test_classify_returns_tuple_of_optional_str_and_float():
    from brainiac.core.classifier import classify
    result = classify("Texto qualquer.")
    assert isinstance(result, tuple)
    assert len(result) == 2
    typ, conf = result
    assert typ is None or isinstance(typ, str)
    assert isinstance(conf, float)
