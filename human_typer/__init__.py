"""Human Typer — realistic keyboard/mouse automation for AI Coding Operator."""

from human_typer.engine import TypingEngine
from human_typer.typos import typo_for
from human_typer.backends import create_keyboard_backend, create_mouse_backend

__all__ = [
    "TypingEngine",
    "typo_for",
    "create_keyboard_backend",
    "create_mouse_backend",
]
