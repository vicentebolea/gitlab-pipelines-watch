import re
from typing import Literal

from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

# Bump when PROMPT, Extraction, scrub or terminal_errors change: knowledge built with another
# version is not comparable with what the watcher extracts, and the watcher refuses to start on it.
EXTRACTION_VERSION = "1"

PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You read the tail of a failed GitLab CI job log and extract the facts needed to compare it with "
     "other failures. Ignore runner boilerplate and cleanup output. Find the error that actually "
     "terminated the job; earlier warnings the job survived are not the cause, include one only if "
     "it explains the cause. Put the root-cause line first in the snippet."),
    ("human", "Job name: {job_name}\nRunner: {runner}\n\nLast error lines before the job ended "
               "(the last one is usually the cause):\n{hint}\n\nLog tail:\n{log}"),
])


ErrorType = Literal[
    "network", "registry", "artifact-upload", "cache", "git", "runner-resources", "timeout",
    "compile", "test-failure", "configuration", "other",
]


class Extraction(BaseModel):
    snippet: str = Field(description="the 3 to 10 verbatim log lines showing the root error, root cause first")
    platform: str = Field(description="lowercase os and toolchain the job ran on, e.g. windows-vs2022, "
                                      "linux-x86_64, macos-arm64; infer from job name, runner and log")
    error_type: ErrorType


def build_extractor(model):
    return PROMPT | init_chat_model(model).with_structured_output(Extraction)


_NOISE = [
    (re.compile(r"^\d{4}-\d\d-\d\dT[\d:.]+Z\s+\w+\s?", re.M), ""),  # timestamp and stream marker
    (re.compile(r"\b(token|correlation_id|id)=\S+"), r"\1=<redacted>"),
    (re.compile(r"glpat-\S+"), "<redacted>"),
    (re.compile(r"^section_(start|end):.*\n?", re.M), ""),
    (re.compile(r"[ \t]+$", re.M), ""),
]


def scrub(snippet):
    """Drop timestamps and strip anything that looks like a secret or unique id."""
    for pattern, repl in _NOISE:
        snippet = pattern.sub(repl, snippet)
    return snippet.strip()


_ERROR_LINE = re.compile(r"\b(ERROR|FATAL|fatal:|error:)", re.I)


def terminal_errors(log, n=4):
    """The last n error lines before the runner's 'Job failed', which is where the cause usually is."""
    lines = [l for l in log.splitlines() if _ERROR_LINE.search(l)]
    lines = [l for l in lines if "Job failed" not in l and not l.startswith("section_")]
    return scrub("\n".join(lines[-n:])) or "(none)"
