"""Open the IDEs side by side, then the control GUI, armed and ready."""

from __future__ import annotations

import os
import sys
import threading
import time

from coding_operator import layout, logs


def _arrange_until_done(timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        placed = layout.arrange_side_by_side()
        if placed and all(placed.values()):
            return
        time.sleep(1.0)


def main() -> None:
    log = logs.setup("start")
    args = sys.argv[1:]
    project = os.path.abspath(args[0]) if args else os.getcwd()
    os.environ.setdefault("OPERATOR_IDE", "Visual Studio Code")

    layout.launch_ides(project)
    deadline = time.time() + 10
    placed: dict[str, bool] = {}
    while time.time() < deadline:
        placed = layout.arrange_side_by_side()
        if placed and all(placed.values()):
            break
        time.sleep(0.5)
    for name, ok in placed.items():
        print(f"{name}: {'placed' if ok else 'not placed'}", flush=True)
    log.info("layout %s", placed)
    if not (placed and all(placed.values())):
        threading.Thread(target=_arrange_until_done, args=(60.0,), daemon=True).start()

    from coding_operator.gui import main as gui_main

    gui_main(project=project, auto_arm=True)


if __name__ == "__main__":
    main()
