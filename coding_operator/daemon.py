"""Headless operator daemon (no Tk) - control API + system-wide Esc stop."""

from __future__ import annotations

import signal
import sys
import time

from coding_operator import logs
from coding_operator.control_state import STATE
from coding_operator.esc_watch import EscWatcher, user_stop_handler
from coding_operator.executor import EXECUTOR
from coding_operator.ipc import ControlAPI


def main() -> None:
    logs.setup("daemon")
    project = ""
    args = sys.argv[1:]
    if args:
        project = args[0]
        STATE.project_root = project
    api = ControlAPI(EXECUTOR)
    api.start()
    STATE.arm()
    print(f"AI Coding Operator daemon on {api.base_url} (armed)", flush=True)
    if project:
        print(f"project_root={project}", flush=True)
    print("Esc is monitored system-wide: it stops typing and notifies the agent. Ctrl+C to quit.", flush=True)

    def notify(line: str) -> None:
        print(line, flush=True)

    watcher = EscWatcher(user_stop_handler(STATE, notify))
    watcher.start()

    def _stop(*_args):
        watcher.stop()
        api.stop()
        EXECUTOR.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
