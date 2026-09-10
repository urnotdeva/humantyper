"""Validate and execute structured coding actions via Human Typer."""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

from human_typer.backends import create_keyboard_backend, create_mouse_backend
from human_typer.engine import TypingEngine
from coding_operator.action_schema import Action, ActionValidationError, is_safe_command
from coding_operator.control_state import STATE, AutomationStatus, ControlState
from coding_operator.focus import FocusGuard
from coding_operator.git_manager import GitManager
from coding_operator.vscode_nav import VSCodeNavigator

log = logging.getLogger("operator.executor")


class Executor:
    def __init__(
        self,
        state: ControlState | None = None,
        keyboard=None,
        mouse=None,
        typing: TypingEngine | None = None,
        wpm: int = 120,
        error_rate: float = 0.0,
        focus_guard: bool = True,
    ):
        self.state = state or STATE
        self._focus = FocusGuard() if focus_guard else None
        self._focus_pauses = 0
        self._kb = keyboard
        self._mouse = mouse
        self._engine = typing
        self.wpm = wpm
        self.error_rate = error_rate
        self._init_lock = threading.Lock()
        self.nav: VSCodeNavigator | None = None
        self.git = GitManager(project_root_provider=lambda: self.state.project_root)

    def _ensure_backends(self) -> None:
        with self._init_lock:
            if self._kb is None:
                self._kb = create_keyboard_backend()
            if self._mouse is None:
                self._mouse = create_mouse_backend()
            if self._engine is None:
                self._engine = TypingEngine(self._kb, pause_event=self.state.pause_event)
            if self.nav is None:
                self.nav = VSCodeNavigator(self._kb)
            self._engine.gate = self._focus_gate
            if self._focus is not None:
                self._focus.start()

    @property
    def engine(self) -> TypingEngine:
        self._ensure_backends()
        assert self._engine is not None
        return self._engine

    def close(self) -> None:
        if self._kb:
            self._kb.close()
        if self._mouse:
            self._mouse.close()

    def execute(self, raw: dict[str, Any] | Action) -> dict[str, Any]:
        try:
            action = raw if isinstance(raw, Action) else Action.from_dict(raw)
        except ActionValidationError as exc:
            self.state.log_action("invalid", str(raw), False, str(exc))
            return {"ok": False, "error": str(exc)}

        # Control actions allowed even when disarmed
        control_ok = {"operator_status", "arm", "disarm", "pause", "resume", "emergency_stop"}
        if action.type not in control_ok and not self.state.armed:
            err = "Operator is disarmed. Call arm or press Arm in the GUI."
            self.state.log_action(action.type, "", False, err)
            return {"ok": False, "error": err}

        if self.state.stop_event.is_set() and action.type not in (
            "operator_status",
            "arm",
            "emergency_stop",
            "resume",
        ):
            if self.state.stopped_by_user:
                return _stopped_by_user_result()
            return {"ok": False, "error": "Operator is stopped. Clear stop / re-arm."}

        self.state.set_status(
            AutomationStatus.RUNNING,
            action=action.type,
            message=f"Executing {action.type}",
        )
        try:
            result = self._dispatch(action)
            self.state.log_action(action.type, _detail(action), True)
            log.info("%s ok %s", action.type, _detail(action))
            if self.state.status != AutomationStatus.PAUSED:
                self.state.set_status(
                    AutomationStatus.IDLE if self.state.armed else AutomationStatus.DISARMED,
                    action="",
                    message="Idle",
                )
            return {"ok": True, **result}
        except InterruptedError:
            self.state.log_action(action.type, _detail(action), False, "typing stopped by user")
            self.state.set_status(AutomationStatus.STOPPED, message="Typing stopped by user")
            return _stopped_by_user_result()
        except Exception as exc:
            self.state.log_action(action.type, _detail(action), False, str(exc))
            log.exception("%s failed", action.type)
            self._try_recover()
            self.state.pause()
            self.state.set_status(
                AutomationStatus.ERROR,
                message=f"Paused after error: {exc}",
            )
            return {"ok": False, "error": str(exc), "paused": True}

    def _try_recover(self) -> None:
        try:
            self._ensure_backends()
            assert self.nav is not None
            self.nav.recover()
        except Exception:
            pass

    def _paste_exact(self, content: str) -> None:
        """Put content on clipboard and paste via Cmd/Ctrl+V for 100% accuracy."""
        import subprocess
        import platform as _plat
        self._ensure_backends()
        assert self.nav is not None
        if _plat.system() == "Darwin":
            proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            assert proc.stdin is not None
            proc.stdin.write(content.encode("utf-8"))
            proc.stdin.close()
            proc.wait(timeout=5)
        else:
            try:
                proc = subprocess.Popen(
                    ["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE
                )
            except FileNotFoundError:
                proc = subprocess.Popen(
                    ["xsel", "--clipboard", "--input"], stdin=subprocess.PIPE
                )
            assert proc.stdin is not None
            proc.stdin.write(content.encode("utf-8"))
            proc.stdin.close()
            proc.wait(timeout=5)
        time.sleep(0.15)
        self.nav.kb.hotkey(self.nav.mod, "v")
        time.sleep(0.25)

    _EVIDENCE_PATTERNS = (
        "generated by cursor",
        "generated with cursor",
        "generated by ai",
        "ai-generated",
        "ai generated",
        "co-authored-by: cursor",
        "written by an ai",
        "as an ai",
        "language model",
        "this file was generated",
        "this code was generated",
        "generated by claude",
        "generated by gpt",
        "generated by copilot",
        "human typer",
        "ai coding operator",
    )

    def _strip_automation_evidence(self, content: str) -> str:
        markers = ("#", "//", "/*", "*", "<!--", ";", "--", '"""', "'''")
        cleaned = []
        for line in content.split("\n"):
            low = line.lower()
            if any(pat in low for pat in self._EVIDENCE_PATTERNS):
                if low.lstrip().startswith(markers):
                    self.state.log_action(
                        "sanitize", "removed automation-evidence comment", True
                    )
                    continue
            cleaned.append(line)
        return "\n".join(cleaned)

    def _focus_gate(self) -> None:
        guard = self._focus
        if guard is None or guard.ok():
            return
        self._focus_pauses += 1
        self.state.set_status(message="Waiting: VS Code is not the active window")
        log.info("typing paused: active window is %s", guard.front)
        waited = 0.0
        while not guard.ok():
            if self.state.stop_event.is_set():
                raise InterruptedError
            time.sleep(0.1)
            waited += 0.1
            if 120.0 < waited:
                raise RuntimeError("VS Code was not the active window for 2 minutes; action aborted")
        self.state.set_status(message="Typing")

    def _ensure_front(self) -> None:
        guard = self._focus
        if guard is None or not guard.enabled:
            return
        assert self.nav is not None
        deadline = time.time() + 3.0
        while time.time() < deadline and guard.current() is None:
            time.sleep(0.05)
        if guard.ok():
            return
        self.nav.focus_ide()
        deadline = time.time() + 4.0
        while time.time() < deadline:
            if guard.ok():
                return
            time.sleep(0.1)
        raise RuntimeError(f"Could not bring VS Code to the front (active window: {guard.front})")

    def _project_path(self, raw: str) -> str:
        path = os.path.expanduser(raw)
        root = self.state.project_root
        if not os.path.isabs(path):
            path = os.path.join(root or os.getcwd(), path)
        path = os.path.realpath(path)
        if root:
            real_root = os.path.realpath(root)
            if path != real_root and not path.startswith(real_root + os.sep):
                raise ActionValidationError(f"Path is outside the project root: {raw}")
        return path

    def _wait_gates(self) -> None:
        while self.state.pause_event.is_set():
            if self.state.stop_event.is_set():
                raise InterruptedError
            time.sleep(0.05)
        if self.state.stop_event.is_set():
            raise InterruptedError
        self.engine.stop_event.clear()
        # Mirror control stop into engine during typing
        if self.state.stop_event.is_set():
            self.engine.stop()

    def _dispatch(self, action: Action) -> dict[str, Any]:
        t = action.type
        p = action.params

        if t == "operator_status":
            snap = self.state.snapshot()
            git_info = self.git.summary()
            if git_info.get("branch"):
                self.state.set_status(branch=git_info["branch"], last_commit=git_info.get("last_commit", ""))
            return {"status": snap.__dict__ | {"git": git_info}}

        if t == "arm":
            self.state.clear_stop()
            self.state.arm()
            if p.get("project_root"):
                self.state.project_root = str(p["project_root"])
            return {"armed": True}

        if t == "disarm":
            self.state.disarm()
            return {"armed": False}

        if t == "pause":
            self.state.pause()
            return {"paused": True}

        if t == "resume":
            self.state.clear_stop()
            self.state.resume()
            return {"paused": False}

        if t == "emergency_stop":
            self.engine.stop()
            self.state.emergency_stop()
            return {"stopped": True}

        self._ensure_backends()
        assert self.nav is not None
        self._wait_gates()

        if t == "focus_ide":
            self.nav.focus_ide()
            return {}

        if t == "create_folder":
            path = self._project_path(str(p["path"]))
            os.makedirs(path, exist_ok=True)
            return {"path": path, "created": True}

        self._ensure_front()

        if t == "open_file":
            path = self._project_path(str(p["path"]))
            line = int(p["line"]) if p.get("line") is not None else None
            self.state.set_status(file=path)
            self.nav.focus_ide()
            self.nav.open_file(path, line=line)
            return {"path": path, "line": line}

        if t == "create_file":
            path = self._project_path(str(p["path"]))
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            existed = os.path.exists(path)
            if not existed:
                with open(path, "a", encoding="utf-8"):
                    pass
            self.state.set_status(file=path)
            time.sleep(0.4)
            self.nav.open_file(path)
            return {"path": path, "created": not existed}

        if t == "goto":
            if "line" in p:
                self.nav.goto_line(int(p["line"]), p.get("column"))
            elif "text" in p:
                self.nav.find_text(str(p["text"]))
            return {}

        if t == "type_text":
            self.nav.focus_editor()
            content = self._strip_automation_evidence(str(p["content"]))
            # exact=True (default): clipboard paste for 100% fidelity into the IDE
            exact = bool(p.get("exact", False))
            skip_ws = bool(p.get("skip_leading_ws", False))

            if exact:
                self._paste_exact(content)
                self.state.set_status(progress=100.0)
                return {"chars": len(content), "mode": "exact_paste"}

            def on_progress(done, total):
                self.state.set_status(progress=100.0 * done / max(total, 1))
                if self.state.stop_event.is_set():
                    self.engine.stop()

            def watch_stop():
                while not self.engine.stop_event.is_set():
                    if self.state.stop_event.is_set():
                        self.engine.stop()
                        return
                    time.sleep(0.05)

            threading.Thread(target=watch_stop, daemon=True).start()
            self.engine.reset_indent = bool(p.get("reset_indent", True))
            self._focus_pauses = 0
            self.engine.type_text(
                content,
                avg_wpm=int(p.get("wpm", self.wpm)),
                wpm_variance_pct=int(p.get("wpm_variance_pct", 20)),
                error_rate=float(p.get("error_rate", 0.0)),
                skip_leading_ws=skip_ws,
                on_progress=on_progress,
                break_manager=None,
            )
            result: dict[str, Any] = {"chars": len(content), "mode": "keystrokes"}
            if self._focus_pauses:
                result["focus_interruptions"] = self._focus_pauses
                result["note"] = (
                    "Typing paused while VS Code was not the active window. "
                    "Save and re-read the file to verify nothing was lost."
                )
            return result

        if t == "find_text":
            self.nav.find_text(str(p["text"]))
            return {}

        if t == "replace_once":
            self.nav.replace_once(str(p["old"]), str(p["new"]))
            return {}

        if t == "select_all":
            self.nav.focus_editor()
            self.nav.select_all()
            return {}

        if t == "delete_selection":
            self.nav.focus_editor()
            self.nav.delete_selection()
            return {}

        if t == "save":
            self.nav.save()
            return {}

        if t == "undo":
            self.nav.undo()
            return {}

        if t == "run_command":
            command = str(p["command"]).strip()
            force = bool(p.get("confirmed", False))
            needs_confirm = (not is_safe_command(command)) or p.get("_destructive")
            if needs_confirm and not force:
                approved = self.state.request_command_confirm(command)
                if not approved:
                    return {"ok": False, "error": "command rejected by user", "command": command}
            self.nav.focus_ide()
            self.nav.open_terminal()
            # type command with moderate speed, fewer typos
            self.engine.type_text(
                command,
                avg_wpm=90,
                wpm_variance_pct=10,
                error_rate=0.0,
                skip_leading_ws=False,
            )
            self._kb.enter()
            time.sleep(0.5)
            self.nav.focus_editor()
            return {"command": command, "note": "Inspect terminal output in the IDE; then Read/verify."}

        if t == "verify_snippet":
            return {
                "note": "Physical buffer capture is limited. Save, then use Cursor Read on the file.",
                "current_file": self.state.current_file,
            }

        if t == "commit_checkpoint":
            message = p.get("message")
            size = p.get("size", "small")
            if not self.state.auto_commit and not p.get("force", False):
                return {
                    "skipped": True,
                    "reason": "Auto Commit is OFF. Use Commit Now in GUI or pass force=true.",
                }
            result = self.git.commit_checkpoint(message=message, size=size)
            if result.get("commit"):
                self.state.set_status(last_commit=result["commit"], branch=result.get("branch", ""))
            return result

        raise ActionValidationError(f"Unhandled action: {t}")


def _stopped_by_user_result() -> dict[str, Any]:
    return {
        "ok": False,
        "error": "Typing stopped by user",
        "stopped_by_user": True,
        "agent_directive": (
            "The user pressed Esc to stop. Stop iterating now: do not retry, "
            "resume, or call any more typing tools. Acknowledge and wait for the user."
        ),
    }


def _detail(action: Action) -> str:
    p = action.params
    if action.type == "type_text":
        c = str(p.get("content", ""))
        return c[:80] + ("…" if len(c) > 80 else "")
    if "path" in p:
        return str(p["path"])
    if "command" in p:
        return str(p["command"])
    return str({k: v for k, v in p.items() if not str(k).startswith("_")})[:120]


# Shared executor for GUI + MCP
EXECUTOR = Executor()
