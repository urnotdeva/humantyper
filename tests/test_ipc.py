"""IPC control API tests."""

from __future__ import annotations

from coding_operator.control_state import ControlState
from coding_operator.executor import Executor
from coding_operator.ipc import ControlAPI, call_action
from human_typer.engine import TypingEngine


class FakeKeyboard:
    name = "fake"

    def type_char(self, ch: str) -> None:
        pass

    def backspace(self) -> None:
        pass

    def enter(self) -> None:
        pass

    def tab(self) -> None:
        pass

    def key(self, name: str) -> None:
        pass

    def hotkey(self, *keys: str) -> None:
        pass

    def close(self) -> None:
        pass


def test_control_api_arm_roundtrip():
    state = ControlState()
    kb = FakeKeyboard()
    ex = Executor(state=state, keyboard=kb, mouse=object(), typing=TypingEngine(kb))
    api = ControlAPI(ex, host="127.0.0.1", port=18765)
    api.start()
    try:
        result = call_action({"type": "arm"}, base_url="http://127.0.0.1:18765")
        assert result["ok"] is True
        assert state.armed is True
        status = call_action({"type": "operator_status"}, base_url="http://127.0.0.1:18765")
        assert status["ok"] is True
        assert status["status"]["armed"] is True
    finally:
        api.stop()
