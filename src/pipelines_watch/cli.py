import argparse
import asyncio
import logging

from .backfill import backfill
from .config import Settings
from .watcher import Watcher


def main():
    parser = argparse.ArgumentParser(prog="pipelines-watch")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("watch", help="poll Prometheus and retry transient failures")
    bf = sub.add_parser("backfill", help="seed the corpus from GitLab history")
    bf.add_argument("project", help="group/project path")
    bf.add_argument("--pipelines", type=int, default=200)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = Settings()
    if args.cmd == "watch":
        asyncio.run(Watcher(cfg).run())
    else:
        backfill(cfg, args.project, args.pipelines)
