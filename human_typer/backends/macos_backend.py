"""macOS-oriented backend wrappers (pynput + Accessibility)."""

from __future__ import annotations

from human_typer.backends.pynput_backend import PynputKeyboardBackend, PynputMouseBackend


class MacOSKeyboardBackend(PynputKeyboardBackend):
    name = "macOS (pynput / Accessibility)"

    def __init__(self):
        super().__init__()
        if self.platform != "Darwin":
            # Still usable; shortcuts remain Cmd-oriented when forced.
            pass


class MacOSMouseBackend(PynputMouseBackend):
    name = "macOS (pynput mouse)"
