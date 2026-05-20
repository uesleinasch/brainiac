"""Sentence-transformers wrapper: lazy load, cache em memória, normalização L2."""

from __future__ import annotations

import logging
from threading import Lock
from typing import Sequence

import numpy as np

_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
_EMBED_DIM = 384

_logger = logging.getLogger(__name__)
_model = None
_load_failed = False
_lock = Lock()


def _get_model():
    """Lazy load do modelo. Em falha, marca _load_failed e propaga exceção."""
    global _model, _load_failed
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(_MODEL_NAME)
            return _model
        except Exception as exc:
            _load_failed = True
            _logger.warning("embeddings: model load failed: %s", exc)
            raise


def model_available() -> bool:
    """True se o modelo já foi carregado com sucesso."""
    return _model is not None and not _load_failed


def embed_texts(texts: Sequence[str]) -> np.ndarray:
    """Embed batch. Retorna float32 (N, 384) normalizados."""
    model = _get_model()
    vecs = model.encode(
        list(texts),
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return vecs.astype(np.float32, copy=False)


def embed_query(text: str) -> np.ndarray:
    """Embed um único texto. Retorna float32 (384,) normalizado."""
    return embed_texts([text])[0]


def reset_for_tests() -> None:
    """Limpa o cache de modelo. Apenas para uso em testes."""
    global _model, _load_failed
    with _lock:
        _model = None
        _load_failed = False
