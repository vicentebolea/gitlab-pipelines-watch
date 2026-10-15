import argparse
import asyncio
import logging

from .config import Settings
from .watcher import Watcher


def main():
    parser = argparse.ArgumentParser(prog="pipelines-watch")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("watch", help="poll Prometheus and retry transient failures")
    parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(Watcher(Settings()).run())
