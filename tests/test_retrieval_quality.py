"""Retrieval quality on the real corpus with the real embedding model.

Needs a built knowledge dir (PW_KNOWLEDGE_DIR, default ./knowledge) and a reachable
embedding backend, so it is excluded from the default run: pytest -m embedding.
"""
import os
import random
from collections import Counter

import pytest

from pipelines_watch.corpus import Corpus
from pipelines_watch.entries import load_all

pytestmark = pytest.mark.embedding

KNOWLEDGE = os.environ.get("PW_KNOWLEDGE_DIR", "knowledge")
MODEL = os.environ.get("PW_EMBEDDING_MODEL", "ollama:nomic-embed-text")
K = 5


@pytest.fixture(scope="module")
def corpus():
    try:
        c = Corpus(KNOWLEDGE, MODEL)
        c.similar("probe", k=1)
    except Exception as e:  # missing corpus or no embedding server
        if os.environ.get("PW_REQUIRE_EMBEDDINGS"):
            raise
        pytest.skip(f"embedding backend or corpus unavailable: {e}")
    return c


@pytest.fixture(scope="module")
def entries():
    return list(load_all(KNOWLEDGE))


def test_every_entry_file_is_indexed(corpus, entries):
    assert len(entries) > 100
    assert all(corpus.has(e.id) for e, _ in entries)


def test_neighbours_share_the_error_type_far_above_chance(corpus, entries):
    """Leave-one-out: the K nearest other entries should mostly have the same error_type."""
    base = Counter(e.error_type for e, _ in entries)
    n = len(entries)
    sample = random.Random(0).sample(entries, min(80, n))
    hits = total = 0
    chance = 0.0
    for e, md in sample:
        docs = [d for d in corpus.similar(e.snippet, K + 1) if d.metadata["markdown"] != md][:K]
        hits += sum(d.metadata["error_type"] == e.error_type for d in docs)
        total += len(docs)
        chance += (base[e.error_type] - 1) / (n - 1) * len(docs)
    precision, chance = hits / total, chance / total
    # Measured 0.85 against 0.20 chance on the vtk corpus.
    assert precision >= 0.6, f"precision@{K} {precision:.2f} (chance {chance:.2f})"
    assert precision >= chance + 0.3


@pytest.mark.parametrize("query, expected", [
    ("error: bad signature 0x00000000\nfatal: index file corrupt", "git"),
    ("ERROR: Uploading artifacts to coordinator... 413 Request Entity Too Large\nFATAL: too large", "artifact-upload"),
])
def test_known_errors_retrieve_their_category(corpus, entries, query, expected):
    if not any(e.error_type == expected for e, _ in entries):
        pytest.skip(f"no {expected} entries in this corpus")
    docs = corpus.similar(query, K)
    assert sum(d.metadata["error_type"] == expected for d in docs) >= 3
