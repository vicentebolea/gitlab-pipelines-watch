import asyncio
import logging

from prometheus_client import Counter, start_http_server

from . import prom
from .corpus import State
from .gitlab import GitLab
from .judge import Judge

log = logging.getLogger(__name__)
DECISIONS = Counter("pw_decisions_total", "Decisions taken", ["result"])


class Watcher:
    def __init__(self, cfg):
        self.cfg = cfg
        self.gl = GitLab(cfg.gitlab_url, cfg.gitlab_token, cfg.gitlab_rps)
        self.judge = Judge(cfg)
        self.state = State(cfg.state_dir)
        self.sem = asyncio.Semaphore(cfg.concurrency)

    async def handle(self, project, job_id, name, reason):
        async with self.sem:
            try:
                job = await self.gl.job(project, job_id)
                await asyncio.to_thread(job.refresh)
                pipeline_id = job.pipeline["id"]
                text = None
                if reason == "script_failure":
                    text = await self.gl.log_tail(job)
                    a = await self.judge.assess(name, text)
                    retry, why = a.retry, a.reason
                else:
                    retry, why = True, f"infrastructure failure: {reason}"
                if self.state.retries(project, pipeline_id, name) >= self.cfg.max_retries_per_job:
                    retry, why = False, "retry cap reached"
                new_id = None
                if retry and not self.cfg.dry_run:
                    new_id = (await self.gl.retry(job))["id"]
                self.state.record(project, job_id, pipeline_id, name, retry, why, new_id)
                DECISIONS.labels("retry" if retry else "skip").inc()
                log.info("%s #%d %s -> %s (%s)", project, job_id, name, "RETRY" if retry else "SKIP", why)
            except Exception:
                DECISIONS.labels("error").inc()
                log.exception("failed handling %s #%d", project, job_id)

    async def cycle(self):
        failed = await asyncio.to_thread(prom.failed_jobs, self.cfg.prometheus_url)
        new = [f for f in failed if not self.state.seen(f[0], f[1])]
        await asyncio.gather(*(self.handle(*f) for f in new))

    async def run(self):
        start_http_server(self.cfg.metrics_port)
        while True:
            try:
                await self.cycle()
            except Exception:
                log.exception("cycle failed")
            await asyncio.sleep(self.cfg.poll_interval)
