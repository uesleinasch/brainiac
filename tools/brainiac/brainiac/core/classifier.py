from __future__ import annotations

import re

_EPISODIC_PATTERNS = [
    r"\bhoje\b", r"\bontem\b", r"\banteontem\b",
    r"\beu fiz\b", r"\beu vi\b", r"\beu li\b", r"\beu consegui\b",
    r"\bdecidimos\b", r"\bdecidi\b",
    r"\bfui ao\b", r"\bfui à\b", r"\bfui em\b",
    r"\bminha reuni[aã]o\b", r"\bnossa reuni[aã]o\b",
    r"\bme contou\b", r"\bme disse\b",
]

_SEMANTIC_PATTERNS = [
    r"\bé uma\b", r"\bé um\b",
    r"\bconsiste em\b",
    r"\brefere-se a\b", r"\bsignifica\b",
    r"\bdefine-se\b", r"\bcaracteriza-se\b",
    r"\btrata-se de\b",
]

_WORKING_TAG_HINTS = {"rascunho", "draft", "ideia", "wip", "todo"}
_EPISODIC_TAG_HINTS = {"pessoal", "diário", "diario", "reunião", "reuniao", "evento"}
_SEMANTIC_TAG_HINTS = {"conceito", "definição", "definicao", "fato", "fórmula", "formula"}

_MARKER_WEIGHT = 0.3
_TAG_WEIGHT = 0.4
_SHORT_BODY_WEIGHT = 0.1
_QUESTION_OR_DRAFT_WEIGHT = 0.3

_SHORT_BODY_CHARS = 80
_AMBIGUITY_MARGIN = 0.15
_DEFAULT_THRESHOLD = 0.3


def classify(
    body: str,
    tags: list[str] | None = None,
    threshold: float = _DEFAULT_THRESHOLD,
) -> tuple[str | None, float]:
    """Heuristic classifier for note type.

    Returns (suggested_type, confidence in [0, 1]).
    Returns (None, 0.0) if confidence is below threshold or top-2 tie is too close.
    """
    tags = tags or []
    body_lower = body.lower()
    score = {"episodic": 0.0, "semantic": 0.0, "working": 0.0}

    for pat in _EPISODIC_PATTERNS:
        if re.search(pat, body_lower):
            score["episodic"] += _MARKER_WEIGHT

    for pat in _SEMANTIC_PATTERNS:
        if re.search(pat, body_lower):
            score["semantic"] += _MARKER_WEIGHT

    if len(body.strip()) < _SHORT_BODY_CHARS:
        score["working"] += _SHORT_BODY_WEIGHT
    tail = body[-30:]
    if "?" in tail or "rascunho" in body_lower or "todo:" in body_lower:
        score["working"] += _QUESTION_OR_DRAFT_WEIGHT

    for t in tags:
        tl = t.lower()
        if tl in _EPISODIC_TAG_HINTS:
            score["episodic"] += _TAG_WEIGHT
        elif tl in _SEMANTIC_TAG_HINTS:
            score["semantic"] += _TAG_WEIGHT
        elif tl in _WORKING_TAG_HINTS:
            score["working"] += _TAG_WEIGHT

    best = max(score, key=score.get)
    best_score = score[best]
    sorted_scores = sorted(score.values(), reverse=True)
    margin = sorted_scores[0] - sorted_scores[1] if len(sorted_scores) > 1 else best_score

    if best_score < threshold:
        return None, 0.0
    if margin < _AMBIGUITY_MARGIN:
        return None, 0.0

    return best, min(best_score, 1.0)
