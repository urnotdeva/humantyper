"""Strict JSON action schemas for operator / MCP payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ALLOWED_ACTIONS = frozenset(
    {
        "operator_status",
        "focus_ide",
        "open_file",
        "create_file",
        "create_folder",
        "goto",
        "type_text",
        "find_text",
        "replace_once",
        "select_all",
        "delete_selection",
        "save",
        "undo",
        "run_command",
        "verify_snippet",
        "commit_checkpoint",
        "pause",
        "resume",
        "emergency_stop",
        "arm",
        "disarm",
    }
)

SAFE_COMMAND_ALLOWLIST = (
    "pytest",
    "python -m pytest",
    "python3 -m pytest",
    "npm test",
    "npm run test",
    "npm run lint",
    "npx tsc --noEmit",
    "ruff check",
    "ruff format --check",
    "mypy",
    "git status",
    "git diff",
    "git log",
    "git branch",
    "ls",
    "pwd",
)

DESTRUCTIVE_PATTERNS = (
    "rm -rf",
    "rm -fr",
    "git reset --hard",
    "git clean -fd",
    "git clean -f",
    "mkfs",
    "dd if=",
    ":(){",
    "chmod -R 777 /",
)


class ActionValidationError(ValueError):
    pass


@dataclass
class Action:
    type: str
    params: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Action":
        if not isinstance(data, dict):
            raise ActionValidationError("Action must be an object")
        # Support either {"type": "...", ...params} or {"type": "...", "params": {...}}
        action_type = data.get("type") or data.get("action")
        if not action_type or not isinstance(action_type, str):
            raise ActionValidationError("Missing action type")
        action_type = action_type.strip().lower()
        if action_type not in ALLOWED_ACTIONS:
            raise ActionValidationError(f"Unknown action type: {action_type}")

        if "params" in data and isinstance(data["params"], dict):
            params = dict(data["params"])
        else:
            params = {k: v for k, v in data.items() if k not in ("type", "action", "params")}

        validate_params(action_type, params)
        return cls(type=action_type, params=params)


def validate_params(action_type: str, params: dict[str, Any]) -> None:
    required: dict[str, tuple[str, ...]] = {
        "open_file": ("path",),
        "create_file": ("path",),
        "create_folder": ("path",),
        "type_text": ("content",),
        "find_text": ("text",),
        "replace_once": ("old", "new"),
        "run_command": ("command",),
        "goto": (),  # line or text
        "commit_checkpoint": (),
    }
    for key in required.get(action_type, ()):
        if key not in params or params[key] in (None, ""):
            raise ActionValidationError(f"{action_type} requires '{key}'")

    if action_type == "goto":
        if "line" not in params and "text" not in params:
            raise ActionValidationError("goto requires 'line' or 'text'")

    if action_type in ("open_file", "create_file", "create_folder"):
        path = str(params["path"])
        if path.startswith("/") and ".." in path.split("/"):
            raise ActionValidationError("Suspicious path")
        if "\x00" in path:
            raise ActionValidationError("Invalid path")

    if action_type == "type_text":
        if not isinstance(params["content"], str):
            raise ActionValidationError("content must be a string")
        if len(params["content"]) > 200_000:
            raise ActionValidationError("content too large; chunk into smaller type_text calls")

    if action_type == "run_command":
        cmd = str(params["command"]).strip()
        if not cmd:
            raise ActionValidationError("empty command")
        lower = cmd.lower()
        for pat in DESTRUCTIVE_PATTERNS:
            if pat in lower:
                params["_destructive"] = True

    if action_type == "commit_checkpoint":
        size = params.get("size", "small")
        if size not in ("small", "medium", "large"):
            raise ActionValidationError("size must be small|medium|large")


def is_safe_command(command: str) -> bool:
    cmd = command.strip()
    lower = cmd.lower()
    for pat in DESTRUCTIVE_PATTERNS:
        if pat in lower:
            return False
    for allowed in SAFE_COMMAND_ALLOWLIST:
        if lower == allowed or lower.startswith(allowed + " "):
            return True
    return False
