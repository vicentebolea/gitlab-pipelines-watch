import re
from pathlib import Path

import yaml
from pydantic import BaseModel

FENCE = "`" * 3
SNIPPET = re.compile(FENCE + r"[^\n]*\n(.*?)\n" + FENCE, re.S)


class Entry(BaseModel):
    """One corpus entry: an error snippet and what a retry did on this job and platform."""

    project: str
    job_id: int
    pipeline_id: int
    ref: str
    job_name: str
    platform: str
    error_type: str
    snippet: str
    outcome: str  # retry_passed | retry_failed

    @property
    def id(self):
        return f"{self.project}:{self.job_id}"

    def to_markdown(self):
        meta = self.model_dump(exclude={"snippet"})
        return (
            f"---\n{yaml.safe_dump(meta, sort_keys=False)}---\n\n"
            f"# {self.error_type} on {self.platform}: {self.outcome}\n\n"
            f"Job `{self.job_name}` ({self.project}). A retry of this job on this platform "
            f"{'passed' if self.outcome == 'retry_passed' else 'failed again'}.\n\n"
            f"{FENCE}text\n{self.snippet}\n{FENCE}\n"
        )

    @classmethod
    def from_markdown(cls, md):
        _, front, body = md.split("---\n", 2)
        return cls(**yaml.safe_load(front), snippet=SNIPPET.search(body).group(1))


def _path(data_dir, project, job_id):
    return Path(data_dir) / "entries" / project.replace("/", "__") / f"{job_id}.md"


def exists(data_dir, project, job_id):
    return _path(data_dir, project, job_id).exists()


def save(data_dir, entry):
    p = _path(data_dir, entry.project, entry.job_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(entry.to_markdown())


def load_all(data_dir):
    """Yield (entry, markdown); hand-edited files are picked up as they are."""
    for p in sorted((Path(data_dir) / "entries").glob("*/*.md")):
        md = p.read_text()
        yield Entry.from_markdown(md), md
