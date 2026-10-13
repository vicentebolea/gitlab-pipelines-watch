from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All settings come from PW_* environment variables (or a .env file)."""

    model_config = SettingsConfigDict(env_prefix="PW_", env_file=".env", extra="ignore")

    gitlab_url: str = "https://gitlab.kitware.com"
    gitlab_token: str
    prometheus_url: str = "http://rigel:9090"

    # LLM and embeddings, resolved by langchain init_chat_model / init_embeddings.
    llm_model: str = "openai:gemini-2.0-flash"
    embedding_model: str = "openai:text-embedding-3-small"

    data_dir: str = "data"
    poll_interval: int = 60
    concurrency: int = 8  # in-flight classifications/retries
    gitlab_rps: float = 5.0  # GitLab API requests per second, shared by all workers
    max_retries_per_job: int = 2  # per (pipeline, job name)
    similar_k: int = 4  # past failures shown to the LLM
    min_confidence: float = 0.6
    dry_run: bool = False
    metrics_port: int = 9100
