"""Shared pynput keyboard/mouse backends with platform hotkey helpers."""

from __future__ import annotations

import platform
import time

from pynput.keyboard import Controller, Key

from human_typer.mouse_path import humanized_path

_KEY_MAP = {
    "enter": Key.enter,
    "return": Key.enter,
    "tab": Key.tab,
    "backspace": Key.backspace,
    "esc": Key.esc,
    "escape": Key.esc,
    "space": Key.space,
    "up": Key.up,
    "down": Key.down,
    "left": Key.left,
    "right": Key.right,
    "home": Key.home,
    "end": Key.end,
    "page_up": Key.page_up,
    "page_down": Key.page_down,
    "delete": Key.delete,
    "shift": Key.shift,
    "ctrl": Key.ctrl,
    "alt": Key.alt,
    "cmd": Key.cmd,
    "command": Key.cmd,
    "option": Key.alt,
    "meta": Key.cmd if platform.system() == "Darwin" else Key.ctrl,
}


def resolve_key(name: str):
    lower = name.lower()
    if lower in _KEY_MAP:
        return _KEY_MAP[lower]
    if len(name) == 1:
        return name
    raise ValueError(f"Unknown key: {name}")


class PynputKeyboardBackend:
    """Cross-platform keyboard via pynput (X11 / macOS Accessibility)."""

    name = "pynput keyboard"

    def __init__(self):
        self.kb = Controller()
        self.platform = platform.system()

    @property
    def mod_key(self) -> str:
        return "cmd" if self.platform == "Darwin" else "ctrl"

    def type_char(self, ch: str) -> None:
        self.kb.type(ch)

    def backspace(self) -> None:
        self.key("backspace")

    def enter(self) -> None:
        self.key("enter")

    def tab(self) -> None:
        self.key("tab")

    def key(self, name: str) -> None:
        k = resolve_key(name)
        self.kb.press(k)
        self.kb.release(k)

    def hotkey(self, *keys: str) -> None:
        resolved = [resolve_key(k) for k in keys]
        for k in resolved:
            self.kb.press(k)
        for k in reversed(resolved):
            self.kb.release(k)

    def ctrl_end(self) -> None:
        """Go to end of document — Cmd+Down on macOS, Ctrl+End elsewhere."""
        if self.platform == "Darwin":
            self.hotkey("cmd", "down")
        else:
            self.hotkey("ctrl", "end")

    def close(self) -> None:
        pass


class PynputMouseBackend:
    name = "pynput mouse"

    def __init__(self):
        from pynput.mouse import Button, Controller as MouseController

        self._Button = Button
        self.m = MouseController()

    def get_position(self):
        return self.m.position

    def human_move(self, start, end, target_width=60.0, stop_event=None):
        points, step_delay = humanized_path(start, end, target_width=target_width)
        for pt in points:
            if stop_event and stop_event.is_set():
                raise InterruptedError
            self.m.position = pt
            time.sleep(step_delay)

    def press_button(self):
        self.m.press(self._Button.left)

    def release_button(self):
        self.m.release(self._Button.left)

    def click(self):
        self.m.click(self._Button.left, 1)

    def close(self):
        pass
