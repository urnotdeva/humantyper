"""Backend factory for macOS / Linux."""

from __future__ import annotations

import platform

from human_typer.backends.linux_backend import (
    EVDEV_AVAILABLE,
    LinuxKeyboardBackend,
    LinuxMouseBackend,
    UInputBackend,
    UInputMouseBackend,
)
from human_typer.backends.macos_backend import MacOSKeyboardBackend, MacOSMouseBackend
from human_typer.backends.pynput_backend import PynputKeyboardBackend, PynputMouseBackend
from human_typer.backends.protocol import KeyboardBackend, MouseBackend

__all__ = [
    "KeyboardBackend",
    "MouseBackend",
    "create_keyboard_backend",
    "create_mouse_backend",
    "EVDEV_AVAILABLE",
]


def create_keyboard_backend(kind: str | None = None):
    """
    kind: 'auto' | 'pynput' | 'macos' | 'linux' | 'uinput'
    """
    system = platform.system()
    choice = (kind or "auto").lower()
    if choice == "auto":
        choice = "macos" if system == "Darwin" else "linux"
    if choice in ("macos", "darwin"):
        return MacOSKeyboardBackend()
    if choice == "uinput":
        return UInputBackend()
    if choice == "linux":
        return LinuxKeyboardBackend()
    if choice == "pynput":
        return PynputKeyboardBackend()
    raise ValueError(f"Unknown keyboard backend: {kind}")


def create_mouse_backend(kind: str | None = None):
    system = platform.system()
    choice = (kind or "auto").lower()
    if choice == "auto":
        choice = "macos" if system == "Darwin" else "linux"
    if choice in ("macos", "darwin"):
        return MacOSMouseBackend()
    if choice == "uinput":
        return UInputMouseBackend()
    if choice == "linux":
        return LinuxMouseBackend()
    if choice == "pynput":
        return PynputMouseBackend()
    raise ValueError(f"Unknown mouse backend: {kind}")
