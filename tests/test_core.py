"""Unit tests for typos, action schema, control state, git helpers."""

from __future__ import annotations

import threading
import time

import pytest

from coding_operator.action_schema import (
    Action,
    ActionValidationError,
    is_safe_command,
)
from coding_operator.control_state import ControlState, AutomationStatus
from human_typer.typos import KEY_ADJACENCY, typo_for
from human_typer.mouse_path import humanized_path
from human_typer.engine import TypingEngine


class FakeKeyboard:
    name = "fake"

    def __init__(self):
        self.chars: list[str] = []
        self.hotkeys: list[tuple] = []
        self.keys: list[str] = []

    def type_char(self, ch: str) -> None:
        self.chars.append(ch)

    def backspace(self) -> None:
        self.keys.append("backspace")
        if self.chars:
            self.chars.pop()

    def enter(self) -> None:
        self.chars.append("\n")

    def tab(self) -> None:
        self.chars.append("\t")

    def key(self, name: str) -> None:
        self.keys.append(name)

    def hotkey(self, *keys: str) -> None:
        self.hotkeys.append(keys)

    def close(self) -> None:
        pass


def test_typo_for_adjacent():
    t = typo_for("a")
    assert t is None or t.lower() in KEY_ADJACENCY["a"]


def test_humanized_path_nonempty():
    pts, delay = humanized_path((0, 0), (100, 100), target_width=40)
    assert len(pts) >= 4
    assert delay > 0


def test_action_validation_open_file():
    a = Action.from_dict({"type": "open_file", "path": "src/main.py"})
    assert a.type == "open_file"
    assert a.params["path"] == "src/main.py"


def test_action_rejects_unknown():
    with pytest.raises(ActionValidationError):
        Action.from_dict({"type": "explode"})


def test_action_type_text_requires_content():
    with pytest.raises(ActionValidationError):
        Action.from_dict({"type": "type_text"})


def test_safe_commands():
    assert is_safe_command("pytest")
    assert is_safe_command("pytest -q")
    assert not is_safe_command("rm -rf /")
    assert not is_safe_command("git reset --hard")


def test_control_state_pause_resume():
    s = ControlState()
    s.arm()
    assert s.status == AutomationStatus.IDLE
    s.pause()
    assert s.pause_event.is_set()
    s.resume()
    assert not s.pause_event.is_set()


def test_typing_engine_with_fake_backend():
    kb = FakeKeyboard()
    engine = TypingEngine(kb)
    engine.type_text(
        "hi",
        avg_wpm=500,
        wpm_variance_pct=5,
        error_rate=0.0,
        skip_leading_ws=False,
    )
    assert "".join(kb.chars) == "hi"


def test_typing_engine_respects_stop():
    kb = FakeKeyboard()
    engine = TypingEngine(kb)

    def stopper():
        time.sleep(0.05)
        engine.stop()

    threading.Thread(target=stopper, daemon=True).start()
    with pytest.raises(InterruptedError):
        engine.type_text(
            "x" * 5000,
            avg_wpm=40,
            wpm_variance_pct=10,
            error_rate=0.0,
            skip_leading_ws=False,
        )


def test_executor_disarmed_blocks_type():
    from coding_operator.executor import Executor
    from coding_operator.control_state import ControlState

    state = ControlState()
    kb = FakeKeyboard()
    ex = Executor(focus_guard=False, state=state, keyboard=kb, mouse=None, typing=TypingEngine(kb, state.pause_event))
    # bypass mouse ensure — patch _ensure to only set kb/engine/nav
    ex._mouse = object()
    from coding_operator.vscode_nav import VSCodeNavigator

    ex.nav = VSCodeNavigator(kb, settle=0.0)

    result = ex.execute({"type": "type_text", "content": "nope"})
    assert result["ok"] is False
    assert "disarmed" in result["error"].lower()

    state.arm()
    result = ex.execute({"type": "type_text", "content": "ok", "wpm": 800, "error_rate": 0, "exact": False})
    assert result["ok"] is True
    assert "ok" in "".join(kb.chars)


def test_interrupt_returns_stopped_by_user():
    from coding_operator.executor import Executor
    from coding_operator.vscode_nav import VSCodeNavigator

    state = ControlState()
    kb = FakeKeyboard()
    engine = TypingEngine(kb, state.pause_event)
    ex = Executor(focus_guard=False, state=state, keyboard=kb, mouse=object(), typing=engine)
    ex.nav = VSCodeNavigator(kb, settle=0.0)
    state.arm()

    def fire():
        time.sleep(0.05)
        state.user_stop()
        engine.stop()

    threading.Thread(target=fire, daemon=True).start()
    result = ex.execute(
        {"type": "type_text", "content": "x" * 4000, "exact": False, "wpm": 60}
    )
    assert result["ok"] is False
    assert result.get("stopped_by_user") is True
    assert "stopped by user" in result["error"].lower()
    assert state.stopped_by_user is True


def test_strip_automation_evidence_only_removes_marker_comments():
    from coding_operator.executor import Executor

    ex = Executor(focus_guard=False, state=ControlState(), keyboard=FakeKeyboard(), mouse=object())
    src = "def f():\n    # Generated by Cursor\n    return 1\n"
    out = ex._strip_automation_evidence(src)
    assert "Generated by Cursor" not in out
    assert "def f():" in out and "return 1" in out
    keep = "cursor = db.cursor()\nname = 'ai generated report'\n"
    assert ex._strip_automation_evidence(keep) == keep
