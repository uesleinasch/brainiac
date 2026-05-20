import numpy as np
import pytest
from unittest.mock import patch

from brainiac.core import embeddings


@pytest.mark.slow
def test_embed_query_returns_normalized_384dim():
    vec = embeddings.embed_query("teste em portugues")
    assert vec.shape == (384,)
    assert vec.dtype == np.float32
    # normalized
    assert abs(float(np.linalg.norm(vec)) - 1.0) < 1e-4


@pytest.mark.slow
def test_embed_texts_batches_and_normalizes():
    vecs = embeddings.embed_texts(["hello", "olá", "criptografia"])
    assert vecs.shape == (3, 384)
    norms = np.linalg.norm(vecs, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-4)


@pytest.mark.slow
def test_semantic_similarity_pt_br():
    a = embeddings.embed_query("criação distribuída de chaves criptográficas")
    b = embeddings.embed_query("DKG protocol — distributed key generation")
    sim = float(np.dot(a, b))
    assert sim > 0.45  # >> overlap lexical (zero)


def test_model_available_is_false_before_load():
    embeddings.reset_for_tests()
    assert embeddings.model_available() is False


def test_embed_query_failure_path_short_circuits():
    embeddings.reset_for_tests()
    with patch("sentence_transformers.SentenceTransformer", side_effect=RuntimeError("mock load error")):
        with pytest.raises(Exception):
            embeddings.embed_query("any text")
    # After failure, model_available() must return False
    assert embeddings.model_available() is False
    # Second call must also raise without re-attempting load
    with pytest.raises(RuntimeError, match="previously failed"):
        embeddings.embed_query("any text again")
    # Restore clean state for other tests
    embeddings.reset_for_tests()
