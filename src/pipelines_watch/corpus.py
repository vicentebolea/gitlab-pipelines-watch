import sqlite3
from pathlib import Path

from langchain.embeddings import init_embeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document


class Corpus:
    """Past job failures with their outcome, in a langchain VectorStore (swap Chroma for pgvector to scale out)."""

    def __init__(self, data_dir, embedding_model):
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        self.store = Chroma(
            collection_name="failures",
            # OpenAI-compatible servers (Gemini, vLLM) reject the token ids langchain sends by default.
            embedding_function=init_embeddings(
                embedding_model,
                **({"check_embedding_ctx_length": False} if embedding_model.startswith("openai:") else {}),
            ),
            persist_directory=str(Path(data_dir) / "chroma"),
        )

    def has(self, entry_id):
        return bool(self.store.get(ids=[entry_id])["ids"])

    def add(self, e, markdown):
        self.store.add_documents(
            [Document(
                page_content=e.snippet,  # only the snippet is embedded
                metadata=dict(job_name=e.job_name, platform=e.platform, error_type=e.error_type,
                              project=e.project, outcome=e.outcome, markdown=markdown),
            )],
            ids=[e.id],
        )

    def similar(self, log, k):
        return self.store.similarity_search(log, k=k)


class State:
    """Dedupe, retry caps and audit log. SQLite, so it is one file next to the corpus."""

    def __init__(self, data_dir):
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(Path(data_dir) / "state.db", check_same_thread=False)
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS decisions (
                project TEXT, job_id INTEGER, pipeline_id INTEGER, job_name TEXT,
                retry INTEGER, reason TEXT, new_job_id INTEGER,
                PRIMARY KEY (project, job_id));
            """
        )

    def seen(self, project, job_id):
        return self.db.execute(
            "SELECT 1 FROM decisions WHERE project=? AND job_id=?", (project, job_id)
        ).fetchone() is not None

    def retries(self, project, pipeline_id, job_name):
        return self.db.execute(
            "SELECT COUNT(*) FROM decisions WHERE project=? AND pipeline_id=? AND job_name=? AND retry=1",
            (project, pipeline_id, job_name),
        ).fetchone()[0]

    def record(self, project, job_id, pipeline_id, job_name, retry, reason, new_job_id=None):
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO decisions VALUES (?,?,?,?,?,?,?)",
                (project, job_id, pipeline_id, job_name, int(retry), reason, new_job_id),
            )
