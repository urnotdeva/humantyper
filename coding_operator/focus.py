"""Track which application owns the active window so typing only lands in the IDE."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import threading
import time

OWNER_NAMES = {
    "Visual Studio Code": "Code",
    "Code": "Code",
    "Cursor": "Cursor",
}


def target_owner() -> str:
    ide = os.environ.get("OPERATOR_IDE", "Visual Studio Code")
    return OWNER_NAMES.get(ide, ide)


def _appkit_available() -> bool:
    try:
        import AppKit  # noqa: F401
    except ImportError:
        return False
    return True


def _frontmost_mac() -> str | None:
    try:
        import AppKit

        app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is not None:
            name = app.localizedName()
            return OWNER_NAMES.get(name, name)
    except Exception:
        pass
    import Quartz

    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    for win in Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []:
        if win.get("kCGWindowLayer") == 0:
            return win.get("kCGWindowOwnerName")
    return None


def _frontmost_linux() -> str | None:
    if not shutil.which("xdotool"):
        return None
    try:
        out = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowclassname"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return None
    name = out.stdout.strip()
    if name.lower() in ("code", "code-oss", "vscodium"):
        return "Code"
    if name.lower() == "cursor":
        return "Cursor"
    return name or None


def available() -> bool:
    if platform.system() == "Darwin":
        try:
            import Quartz  # noqa: F401
        except ImportError:
            return False
        return True
    return shutil.which("xdotool") is not None


def frontmost_app() -> str | None:
    try:
        if platform.system() == "Darwin":
            return _frontmost_mac()
        return _frontmost_linux()
    except Exception:
        return None


class FocusGuard:
    def __init__(self, interval: float = 0.05):
        self.interval = interval
        self.front: str | None = None
        self.enabled = available()
        self._fast = platform.system() == "Darwin" and _appkit_available()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.enabled or self._fast or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            self.front = frontmost_app()
            time.sleep(self.interval)

    def current(self) -> str | None:
        if self._fast:
            self.front = frontmost_app()
        return self.front

    def ok(self) -> bool:
        if not self.enabled:
            return True
        return self.current() == target_owner()
