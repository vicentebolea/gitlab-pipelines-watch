import asyncio
import re

import gitlab
from aiolimiter import AsyncLimiter

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
LOG_TAIL_CHARS = 12000


class GitLab:
    """Async facade over python-gitlab: threads for blocking calls, one shared rate limiter."""

    def __init__(self, url, token, rps):
        self.gl = gitlab.Gitlab(url, private_token=token, retry_transient_errors=True)
        self.limiter = AsyncLimiter(max(1, int(rps)), 1)

    async def _call(self, fn, *args):
        async with self.limiter:
            return await asyncio.to_thread(fn, *args)

    async def job(self, project, job_id):
        return await self._call(lambda: self.gl.projects.get(project, lazy=True).jobs.get(job_id))

    async def log_tail(self, job):
        trace = await self._call(job.trace)
        return ANSI.sub("", trace.decode(errors="replace"))[-LOG_TAIL_CHARS:]

    async def retry(self, job):
        await self._call(job.retry)
        return job.attributes  # python-gitlab refreshes attributes with the new job
