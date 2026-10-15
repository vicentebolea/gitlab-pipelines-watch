import json
from pathlib import Path

from .extract import EXTRACTION_VERSION

NAME = "manifest.json"


def write(knowledge_dir, embedding_model, entries):
    """Called by the knowledge builder, so the watcher can tell what the corpus was built with."""
    (Path(knowledge_dir) / NAME).write_text(json.dumps(
        {"embedding_model": embedding_model, "extraction_version": EXTRACTION_VERSION, "entries": entries},
        indent=2) + "\n")


def check(knowledge_dir, embedding_model):
    """Refuse a corpus built with a different embedding model or extraction version."""
    path = Path(knowledge_dir) / NAME
    if not path.exists():
        raise RuntimeError(f"{path} is missing: mount a vtk-pipelines-knowledge image built for this version")
    m = json.loads(path.read_text())
    problems = []
    if m["embedding_model"] != embedding_model:
        problems.append(f"embedding model {m['embedding_model']!r} != configured {embedding_model!r}")
    if m["extraction_version"] != EXTRACTION_VERSION:
        problems.append(f"extraction version {m['extraction_version']!r} != {EXTRACTION_VERSION!r}")
    if problems:
        raise RuntimeError("knowledge is incompatible: " + "; ".join(problems))
    return m
