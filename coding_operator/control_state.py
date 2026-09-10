"""Shared operator control state: arm/pause/stop, status, action log."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable


class AutomationStatus(str, Enum):
    DISARMED = "disarmed"
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"
    AWAITING_CONFIRM = "awaiting_confirm"


@dataclass
class ActionLogEntry:
    ts: float
    action_type: str
    detail: str
    ok: bool
    error: str | None = None


@dataclass
class OperatorSnapshot:
    armed: bool
    status: str
    current_task: str
    current_action: str
    current_file: str
    progress: float
    branch: str
    last_commit: str
    message: str
    auto_commit: bool
    queue_depth: int
    last_actions: list[dict[str, Any]] = field(default_factory=list)


class ControlState:
    def __init__(self, max_log: int = 200):
        self._lock = threading.RLock()
        self.armed = False
        self.status = AutomationStatus.DISARMED
        self.current_task = ""
        self.current_action = ""
        self.current_file = ""
        self.progress = 0.0
        self.branch = ""
        self.last_commit = ""
        self.message = "Disarmed"
        self.auto_commit = False
        self.project_root = ""
        self.pause_event = threading.Event()
        self.stop_event = threading.Event()
        self._log: deque[ActionLogEntry] = deque(maxlen=max_log)
        self._listeners: list[Callable[[], None]] = []
        self._confirm_lock = threading.Lock()
        self._confirm_result: bool | None = None
        self._confirm_event = threading.Event()
        self._pending_command = ""
        self.stopped_by_user = False
        self.last_action_ts = 0.0

    def add_listener(self, cb: Callable[[], None]) -> None:
        self._listeners.append(cb)

    def _notify(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                pass

    def arm(self) -> None:
        with self._lock:
            self.armed = True
            self.stop_event.clear()
            self.stopped_by_user = False
            self.pause_event.clear()
            self.status = AutomationStatus.IDLE
            self.message = "Armed — ready for MCP actions"
        self._notify()

    def disarm(self) -> None:
        with self._lock:
            self.armed = False
            self.status = AutomationStatus.DISARMED
            self.message = "Disarmed"
        self._notify()

    def pause(self) -> None:
        with self._lock:
            self.pause_event.set()
            self.status = AutomationStatus.PAUSED
            self.message = "Paused"
        self._notify()

    def resume(self) -> None:
        with self._lock:
            self.pause_event.clear()
            if self.armed:
                self.status = AutomationStatus.RUNNING if self.current_action else AutomationStatus.IDLE
                self.message = "Resumed"
        self._notify()

    def emergency_stop(self) -> None:
        with self._lock:
            self.stop_event.set()
            self.pause_event.clear()
            self.status = AutomationStatus.STOPPED
            self.message = "Emergency stop"
            self.current_action = ""
        self._notify()

    def user_stop(self) -> None:
        with self._lock:
            self.stop_event.set()
            self.stopped_by_user = True
            self.pause_event.clear()
            self.status = AutomationStatus.STOPPED
            self.message = "Typing stopped by user"
            self.current_action = ""
        self._notify()

    def clear_stop(self) -> None:
        with self._lock:
            self.stop_event.clear()
            self.stopped_by_user = False
            if self.armed and self.status == AutomationStatus.STOPPED:
                self.status = AutomationStatus.IDLE
                self.message = "Ready"

    def set_status(
        self,
        status: AutomationStatus | None = None,
        *,
        action: str | None = None,
        file: str | None = None,
        task: str | None = None,
        progress: float | None = None,
        message: str | None = None,
        branch: str | None = None,
        last_commit: str | None = None,
    ) -> None:
        with self._lock:
            if status is not None:
                self.status = status
            if action is not None:
                self.current_action = action
            if file is not None:
                self.current_file = file
            if task is not None:
                self.current_task = task
            if progress is not None:
                self.progress = progress
            if message is not None:
                self.message = message
            if branch is not None:
                self.branch = branch
            if last_commit is not None:
                self.last_commit = last_commit
        self._notify()

    def log_action(self, action_type: str, detail: str, ok: bool, error: str | None = None) -> None:
        with self._lock:
            self.last_action_ts = time.time()
            self._log.append(
                ActionLogEntry(
                    ts=time.time(),
                    action_type=action_type,
                    detail=detail,
                    ok=ok,
                    error=error,
                )
            )
        self._notify()

    def set_auto_commit(self, enabled: bool) -> None:
        with self._lock:
            self.auto_commit = enabled
            self.message = f"Auto Commit {'ON' if enabled else 'OFF'}"
        self._notify()

    def request_command_confirm(self, command: str, timeout: float = 120.0) -> bool:
        """Block until GUI confirms/denies. Returns False on timeout."""
        with self._confirm_lock:
            self._pending_command = command
            self._confirm_result = None
            self._confirm_event.clear()
        self.set_status(
            AutomationStatus.AWAITING_CONFIRM,
            message=f"Confirm command: {command}",
        )
        self._notify()
        ok = self._confirm_event.wait(timeout=timeout)
        with self._confirm_lock:
            result = bool(self._confirm_result) if ok else False
            self._pending_command = ""
            self._confirm_result = None
        return result

    def resolve_command_confirm(self, approved: bool) -> None:
        with self._confirm_lock:
            self._confirm_result = approved
            self._confirm_event.set()

    @property
    def pending_command(self) -> str:
        with self._confirm_lock:
            return self._pending_command

    def snapshot(self) -> OperatorSnapshot:
        with self._lock:
            return OperatorSnapshot(
                armed=self.armed,
                status=self.status.value,
                current_task=self.current_task,
                current_action=self.current_action,
                current_file=self.current_file,
                progress=self.progress,
                branch=self.branch,
                last_commit=self.last_commit,
                message=self.message,
                auto_commit=self.auto_commit,
                queue_depth=0,
                last_actions=[asdict(e) for e in list(self._log)[-20:]],
            )


# Process-wide singleton used by GUI + MCP
STATE = ControlState()
