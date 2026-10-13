import logging
from itertools import groupby

import gitlab

from .corpus import Corpus
from .gitlab import ANSI, LOG_TAIL_CHARS

log = logging.getLogger(__name__)


def backfill(cfg, project_path, pipelines=200):
    """Seed the corpus from recent pipelines: label each failed job by what its next attempt did."""
    gl = gitlab.Gitlab(cfg.gitlab_url, private_token=cfg.gitlab_token, retry_transient_errors=True)
    project = gl.projects.get(project_path, lazy=True)
    corpus = Corpus(cfg.data_dir, cfg.embedding_model)
    done = 0
    for pipe in _take(project.pipelines.list(per_page=100, iterator=True), pipelines):
        jobs = sorted(pipe.jobs.list(include_retried=True, get_all=True), key=lambda j: (j.name, j.id))
        for name, attempts in groupby(jobs, key=lambda j: j.name):
            attempts = list(attempts)
            for i, j in enumerate(attempts):
                if j.status != "failed" or j.failure_reason != "script_failure":
                    continue
                if i + 1 == len(attempts):
                    continue  # never retried: no evidence either way
                outcome = "retry_passed" if attempts[i + 1].status == "success" else "retry_failed"
                text = ANSI.sub("", project.jobs.get(j.id, lazy=True).trace().decode(errors="replace"))
                corpus.add(j.id, name, project_path, j.failure_reason, text[-LOG_TAIL_CHARS:], outcome)
                done += 1
    log.info("backfilled %d failures from %s", done, project_path)


def _take(it, n):
    for i, x in enumerate(it):
        if i >= n:
            return
        yield x
