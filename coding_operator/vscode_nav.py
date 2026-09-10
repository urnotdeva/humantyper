"""VS Code / Cursor keyboard navigation helpers."""

from __future__ import annotations

import os
import platform
import time

from coding_operator import esc_watch


class VSCodeNavigator:
    """Keyboard-first IDE control. Assumes Cursor/VS Code is already open."""

    def __init__(self, keyboard, settle: float = 0.25):
        self.kb = keyboard
        self.settle = settle
        self.platform = platform.system()
        self.mod = "cmd" if self.platform == "Darwin" else "ctrl"

    def _pause(self, scale: float = 1.0) -> None:
        time.sleep(self.settle * scale)

    def _esc(self) -> None:
        esc_watch.suppress()
        self.kb.key("escape")

    def focus_ide(self) -> None:
        """Best-effort focus Cursor/VS Code via OS helpers; no-op if unavailable."""
        if self.platform == "Darwin":
            import subprocess

            preferred = os.environ.get("OPERATOR_IDE", "Visual Studio Code")
            apps = (preferred,) + tuple(
                app for app in ("Cursor", "Visual Studio Code", "Code") if app != preferred
            )
            for app in apps:
                r = subprocess.run(
                    ["open", "-a", app],
                    capture_output=True,
                    timeout=3,
                )
                if r.returncode == 0:
                    self._pause(1.5)
                    return
        else:
            import subprocess

            for name in ("cursor", "code", "Code", "Cursor"):
                r = subprocess.run(
                    ["wmctrl", "-a", name],
                    capture_output=True,
                    timeout=2,
                )
                if r.returncode == 0:
                    self._pause(1.5)
                    return
        self._pause()

    def quick_open(self, path: str) -> None:
        self.kb.hotkey(self.mod, "p")
        self._pause(1.2)
        # Clear previous query
        self.kb.hotkey(self.mod, "a")
        self._pause(0.3)
        for ch in path:
            if ch == "\n":
                continue
            self.kb.type_char(ch)
            time.sleep(0.015)
        self._pause(0.8)
        self.kb.enter()
        self._pause(1.2)

    def open_file(self, path: str, line: int | None = None) -> None:
        self.quick_open(path)
        if line is not None:
            self.goto_line(line)

    def create_file(self, path: str) -> None:
        """Create via Quick Open typing new path then confirm (Cursor/VS Code)."""
        self.kb.hotkey(self.mod, "n")  # new untitled — then save-as path
        self._pause(1.0)
        self.save_as(path)

    def save_as(self, path: str) -> None:
        self.kb.hotkey(self.mod, "shift", "s")
        self._pause(1.2)
        self.kb.hotkey(self.mod, "a")
        self._pause(0.2)
        for ch in path:
            self.kb.type_char(ch)
            time.sleep(0.015)
        self._pause(0.4)
        self.kb.enter()
        self._pause(1.0)
        # Dismiss overwrite dialog with Enter if shown
        self.kb.enter()
        self._pause(0.5)

    def save(self) -> None:
        self.kb.hotkey(self.mod, "s")
        self._pause()

    def undo(self) -> None:
        self.kb.hotkey(self.mod, "z")
        self._pause()

    def select_all(self) -> None:
        self.kb.hotkey(self.mod, "a")
        self._pause()

    def delete_selection(self) -> None:
        self.kb.key("backspace")
        self._pause(0.5)

    def goto_line(self, line: int, column: int | None = None) -> None:
        self.kb.hotkey(self.mod, "g")
        self._pause(0.8)
        self.kb.hotkey(self.mod, "a")
        text = str(int(line))
        if column is not None:
            text = f"{int(line)}:{int(column)}"
        for ch in text:
            self.kb.type_char(ch)
            time.sleep(0.02)
        self.kb.enter()
        self._pause()

    def find_text(self, text: str) -> None:
        self.kb.hotkey(self.mod, "f")
        self._pause(0.8)
        self.kb.hotkey(self.mod, "a")
        for ch in text:
            self.kb.type_char(ch)
            time.sleep(0.015)
        self._pause(0.5)
        self._esc()
        self._pause(0.3)

    def replace_once(self, old: str, new: str) -> None:
        # Open replace UI
        if self.platform == "Darwin":
            self.kb.hotkey("cmd", "alt", "f")
        else:
            self.kb.hotkey("ctrl", "h")
        self._pause(1.0)
        self.kb.hotkey(self.mod, "a")
        for ch in old:
            self.kb.type_char(ch)
            time.sleep(0.012)
        self.kb.key("tab")
        self._pause(0.3)
        self.kb.hotkey(self.mod, "a")
        for ch in new:
            self.kb.type_char(ch)
            time.sleep(0.012)
        self._pause(0.3)
        # Replace one occurrence (Enter in replace field often finds; Cmd/Ctrl+Shift+1 varies)
        # Use Alt+Cmd+Enter is replace all — avoid. Press Enter to find then replace button shortcut.
        if self.platform == "Darwin":
            self.kb.hotkey("cmd", "shift", "1")  # replace (common binding)
        else:
            self.kb.hotkey("ctrl", "shift", "1")
        self._pause(0.5)
        self._esc()
        self._pause(0.3)

    def open_terminal(self) -> None:
        if self.platform == "Darwin":
            self.kb.hotkey("ctrl", "`")
        else:
            self.kb.hotkey("ctrl", "`")
        self._pause(1.0)

    def focus_editor(self) -> None:
        # Escape closes palettes; Cmd/Ctrl+1 focuses first editor group
        self._esc()
        self._pause(0.2)
        self.kb.hotkey(self.mod, "1")
        self._pause(0.4)

    def recover(self) -> None:
        """Attempt to leave dialogs and return to editor."""
        for _ in range(3):
            self._esc()
            time.sleep(0.15)
        self.focus_editor()
