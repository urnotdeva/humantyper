"""File logging plus crash traces for every operator process."""

from __future__ import annotations

import atexit
import faulthandler
import logging
import os
import sys
from pathlib import Path

LOG_DIR = Path(os.environ.get("OPERATOR_LOG_DIR", Path.home() / ".ai-coding-operator"))
_crash_file = None


def setup(name: str) -> logging.Logger:
    global _crash_file
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.FileHandler(LOG_DIR / "operator.log", encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(process)d %(name)s %(levelname)s %(message)s")
        )
        root.addHandler(handler)
        root.setLevel(logging.INFO)
    if _crash_file is None:
        _crash_file = open(LOG_DIR / "crash.log", "a", encoding="utf-8")
        faulthandler.enable(_crash_file, all_threads=True)
    log = logging.getLogger(name)
    log.info("start pid=%s argv=%s", os.getpid(), sys.argv)
    atexit.register(lambda: log.info("exit pid=%s", os.getpid()))
    return log
