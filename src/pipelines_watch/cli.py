import argparse
import asyncio
import logging
import sys

from . import manifest
from .config import Settings
from .judge import Judge


def diagnose(cfg, args):
    """Say whether a retry is a good idea for a pasted job log, and why."""
    text = args.text or (open(args.file).read() if args.file and args.file != "-" else sys.stdin.read())
    a = asyncio.run(Judge(cfg).assess(args.job, text))
    print(f"platform:   {a.platform}")
    print(f"error type: {a.error_type}")
    print("snippet:\n  " + a.snippet.replace("\n", "\n  "))
    print(f"\nverdict:    {'RETRY' if a.retry else 'DO NOT RETRY'} "
          f"(confidence {a.confidence:.2f}, threshold {cfg.min_confidence})")
    print(f"reason:     {a.reason}")
    print(f"\n{len(a.similar)} similar past failures:")
    for d in a.similar:
        m = d.metadata
        print(f"  [{m['outcome']}] {m['job_name']} ({m['platform']}): {d.page_content.splitlines()[0][:90]}")


def main():
    parser = argparse.ArgumentParser(prog="pipelines-watch")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("watch", help="poll Prometheus and retry transient failures")
    sub.add_parser("check", help="check the mounted knowledge is compatible with this version")
    d = sub.add_parser("diagnose", help="say whether a retry is a good idea for a job log")
    d.add_argument("file", nargs="?", help="log file, or - for stdin (default: stdin)")
    d.add_argument("--text", help="the log text itself, instead of a file")
    d.add_argument("--job", default="unknown", help="job name, helps to infer the platform")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = Settings()
    if args.cmd == "check":
        print(manifest.check(cfg.knowledge_dir, cfg.embedding_model))
    elif args.cmd == "diagnose":
        diagnose(cfg, args)
    else:
        if not cfg.gitlab_token:
            parser.error("watch needs PW_GITLAB_TOKEN")
        from .watcher import Watcher  # imported here: `check` and `diagnose` need no GitLab or Prometheus
        asyncio.run(Watcher(cfg).run())
