"""System-wide Esc detection that ignores the operator's own Esc presses."""

from __future__ import annotations

import platform
import threading
import time
from typing import Callable

from coding_operator.control_state import AutomationStatus, ControlState

_suppress_until = 0.0
_suppress_lock = threading.Lock()


def suppress(seconds: float = 0.4) -> None:
    global _suppress_until
    with _suppress_lock:
        _suppress_until = max(_suppress_until, time.time() + seconds)


def _suppressed() -> bool:
    return time.time() < _suppress_until


def user_stop_handler(
    state: ControlState, notify: Callable[[str], None] | None = None
) -> Callable[[], None]:
    def handler() -> None:
        if not state.armed:
            return
        active = state.status in (AutomationStatus.RUNNING, AutomationStatus.PAUSED)
        recent = time.time() - state.last_action_ts < 3.0
        if not (active or recent):
            return
        state.user_stop()
        state.log_action("esc", "user pressed Esc", False, "Typing stopped by user")
        if notify is not None:
            notify("Esc: typing stopped by user")

    return handler


class EscWatcher:
    def __init__(self, on_esc: Callable[[], None], poll: float = 0.02):
        self._on_esc = on_esc
        self._poll = poll
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._listener = None

    def start(self) -> None:
        if platform.system() == "Darwin":
            self._thread = threading.Thread(target=self._poll_mac, daemon=True)
            self._thread.start()
            return
        from pynput.keyboard import Key, Listener

        def on_press(key):
            if key == Key.esc:
                self._fire()

        self._listener = Listener(on_press=on_press)
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        self._stop.set()
        if self._listener is not None:
            self._listener.stop()

    def _fire(self) -> None:
        if _suppressed():
            return
        try:
            self._on_esc()
        except Exception:
            pass

    def _poll_mac(self) -> None:
        import ctypes
        import ctypes.util

        lib = ctypes.CDLL(ctypes.util.find_library("ApplicationServices"))
        lib.CGEventSourceKeyState.restype = ctypes.c_bool
        lib.CGEventSourceKeyState.argtypes = [ctypes.c_int, ctypes.c_uint16]
        was_down = False
        while not self._stop.is_set():
            down = bool(lib.CGEventSourceKeyState(0, 53)) or bool(
                lib.CGEventSourceKeyState(1, 53)
            )
            if down and not was_down:
                self._fire()
            was_down = down
            time.sleep(self._poll)
