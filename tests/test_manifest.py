import pytest

from pipelines_watch import manifest


def test_matching_manifest_passes(tmp_path):
    manifest.write(tmp_path, "ollama:nomic-embed-text", 425)
    assert manifest.check(tmp_path, "ollama:nomic-embed-text")["entries"] == 425


def test_missing_manifest_is_refused(tmp_path):
    with pytest.raises(RuntimeError, match="manifest.json is missing"):
        manifest.check(tmp_path, "ollama:nomic-embed-text")


def test_embedding_model_mismatch_is_refused(tmp_path):
    manifest.write(tmp_path, "ollama:nomic-embed-text", 1)
    with pytest.raises(RuntimeError, match="embedding model"):
        manifest.check(tmp_path, "openai:text-embedding-3-small")


def test_extraction_version_mismatch_is_refused(tmp_path, monkeypatch):
    manifest.write(tmp_path, "m", 1)
    monkeypatch.setattr(manifest, "EXTRACTION_VERSION", "99")
    with pytest.raises(RuntimeError, match="extraction version"):
        manifest.check(tmp_path, "m")
