import asyncio
import logging
from dataclasses import dataclass

from . import manifest
from .classifier import build_chain, format_examples
from .corpus import Corpus
from .extract import build_extractor, scrub, terminal_errors

log = logging.getLogger(__name__)


@dataclass
class Assessment:
    platform: str
    error_type: str
    snippet: str
    similar: list  # past failures shown to the LLM
    confidence: float
    reason: str
    retry: bool  # the LLM says retry and is confident enough


class Judge:
    """Decides whether a failed job's log is worth a retry. Shared by the watcher and `diagnose`."""

    def __init__(self, cfg):
        self.cfg = cfg
        log.info("knowledge: %s", manifest.check(cfg.knowledge_dir, cfg.embedding_model))
        self.corpus = Corpus(cfg.knowledge_dir, cfg.embedding_model)
        self.chain = build_chain(cfg.llm_model)
        self.extractor = build_extractor(cfg.extract_model)

    async def assess(self, job_name, text, runner=""):
        x = await self.extractor.ainvoke(
            {"job_name": job_name, "runner": runner, "hint": terminal_errors(text), "log": text})
        snippet = scrub(x.snippet)
        docs = await asyncio.to_thread(self.corpus.similar, snippet, self.cfg.similar_k)
        d = await self.chain.ainvoke({"examples": format_examples(docs), "job_name": job_name,
                                      "platform": x.platform, "error_type": x.error_type, "log": snippet})
        return Assessment(x.platform, x.error_type, snippet, docs, d.confidence, d.reason,
                          d.retry and d.confidence >= self.cfg.min_confidence)
