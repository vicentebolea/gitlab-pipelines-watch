import argparse
import asyncio
import logging

from .backfill import backfill, load
from .config import Settings
from .watcher import Watcher


def main():
    parser = argparse.ArgumentParser(prog="pipelines-watch")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("watch", help="poll Prometheus and retry transient failures")
    sub.add_parser("load", help="embed entry files into Chroma")
    bf = sub.add_parser("backfill", help="write corpus entry files from GitLab history")
    bf.add_argument("project", help="group/project path")
    bf.add_argument("--pipelines", type=int, default=200)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = Settings()
    if args.cmd == "watch":
        asyncio.run(Watcher(cfg).run())
    elif args.cmd == "load":
        load(cfg)
    else:
        backfill(cfg, args.project, args.pipelines)
