from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All settings come from PW_* environment variables (or a .env file)."""

    model_config = SettingsConfigDict(env_prefix="PW_", env_file=".env", extra="ignore")

    gitlab_url: str = "https://gitlab.kitware.com"
    gitlab_token: str = ""  # only `watch` needs it
    prometheus_url: str = "http://rigel:9090"

    # LLM and embeddings, resolved by langchain init_chat_model / init_embeddings.
    llm_model: str = "anthropic:claude-sonnet-5-5"
    extract_model: str = "anthropic:claude-haiku-5-5"
    embedding_model: str = "ollama:nomic-embed-text"

    knowledge_dir: str = "knowledge"  # entries (committed) and chroma (built); shipped as an image
    state_dir: str = "data"  # watcher decision log, never shipped
    poll_interval: int = 60
    concurrency: int = 8  # in-flight classifications/retries
    gitlab_rps: float = 5.0  # GitLab API requests per second, shared by all workers
    max_retries_per_job: int = 2  # per (pipeline, job name)
    similar_k: int = 4  # past failures shown to the LLM
    min_confidence: float = 0.6
    dry_run: bool = False
    metrics_port: int = 9101  # 9100 is node_exporter
