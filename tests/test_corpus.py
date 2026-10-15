import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding

from pipelines_watch.classifier import format_examples
from pipelines_watch.corpus import Corpus
from pipelines_watch.entries import Entry

SNIPPETS = {
    "network": "ERROR: dial tcp: lookup registry.example.com: i/o timeout",
    "git": "error: bad signature 0x00000000\nfatal: index file corrupt",
    "compile": "error: expected ';' before '}' token",
}


def entry(job_id, error_type, outcome="retry_passed"):
    return Entry(project="g/p", job_id=job_id, pipeline_id=1, ref="main", job_name=f"build-{job_id}:test",
                 platform="linux-x86_64", error_type=error_type, snippet=SNIPPETS[error_type], outcome=outcome)


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    # Fake embeddings: identical text gives identical vectors, so exact matches rank first.
    monkeypatch.setattr("pipelines_watch.corpus.init_embeddings", lambda *a, **k: DeterministicFakeEmbedding(size=64))
    c = Corpus(tmp_path, "fake:model")
    for i, error_type in enumerate(SNIPPETS, start=1):
        e = entry(i, error_type)
        c.add(e, e.to_markdown())
    return c


def test_has(corpus):
    assert corpus.has("g/p:1")
    assert not corpus.has("g/p:99")


def test_exact_snippet_is_the_top_hit(corpus):
    for error_type, snippet in SNIPPETS.items():
        assert corpus.similar(snippet, k=3)[0].metadata["error_type"] == error_type


def test_only_the_snippet_is_embedded(corpus):
    top = corpus.similar(SNIPPETS["git"], k=1)[0]
    assert top.page_content == SNIPPETS["git"]
    assert top.metadata["markdown"].startswith("---\n")
    assert SNIPPETS["git"] in top.metadata["markdown"]


def test_metadata_carries_platform_and_outcome(corpus):
    top = corpus.similar(SNIPPETS["network"], k=1)[0]
    assert (top.metadata["platform"], top.metadata["outcome"]) == ("linux-x86_64", "retry_passed")


def test_k_limits_results(corpus):
    assert len(corpus.similar(SNIPPETS["git"], k=2)) == 2


def test_format_examples_shows_whole_markdown_files(corpus):
    docs = corpus.similar(SNIPPETS["git"], k=2)
    text = format_examples(docs)
    assert all(d.metadata["markdown"] in text for d in docs)
    assert format_examples([]) == "(none)"
