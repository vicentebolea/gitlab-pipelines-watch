import asyncio
from types import SimpleNamespace

from langchain_core.documents import Document

from pipelines_watch.config import Settings
from pipelines_watch.judge import Judge


class Stub:
    def __init__(self, result):
        self.result, self.seen = result, None

    async def ainvoke(self, inputs):
        self.seen = inputs
        return self.result


def make_judge(retry, confidence):
    j = Judge.__new__(Judge)  # skip the manifest check and the real models
    j.cfg = Settings(min_confidence=0.6)
    doc = Document(page_content="fatal: index file corrupt", metadata={"markdown": "MD", "outcome": "retry_passed"})
    j.corpus = SimpleNamespace(similar=lambda snippet, k: [doc])
    j.extractor = Stub(SimpleNamespace(snippet="2026-10-13T13:26:47.7Z 01E fatal: index file corrupt token=abc",
                                       platform="windows-vs2022", error_type="git"))
    j.chain = Stub(SimpleNamespace(retry=retry, confidence=confidence, reason="because"))
    return j


def test_confident_retry_is_a_retry():
    a = asyncio.run(make_judge(True, 0.9).assess("build:test", "log"))
    assert a.retry and a.platform == "windows-vs2022" and len(a.similar) == 1


def test_low_confidence_retry_is_not_a_retry():
    assert not asyncio.run(make_judge(True, 0.3).assess("build:test", "log")).retry


def test_snippet_is_scrubbed_and_examples_reach_the_prompt():
    j = make_judge(False, 0.9)
    a = asyncio.run(j.assess("build:test", "log"))
    assert a.snippet == "fatal: index file corrupt token=<redacted>"
    assert j.chain.seen["examples"] == "MD" and j.chain.seen["platform"] == "windows-vs2022"
