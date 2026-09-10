"""stdio MCP server exposing Human Typer / operator tools to Cursor."""

from __future__ import annotations

import json
import sys
from typing import Any

import os

from coding_operator.ipc import call_action


def _api_up() -> bool:
    try:
        return bool(call_action({"type": "operator_status"}).get("ok"))
    except Exception:
        return False


def _launch_operator(project_root: str = "") -> dict[str, Any]:
    """Start the control GUI (which opens VS Code beside Cursor and arms) if it is not running."""
    import subprocess
    import time

    if _api_up():
        return {"ok": True, "already_running": True}
    root = project_root or os.environ.get("OPERATOR_PROJECT") or os.getcwd()
    env = dict(os.environ)
    env.setdefault("OPERATOR_IDE", "Visual Studio Code")
    subprocess.Popen(
        [sys.executable, "-m", "coding_operator.start", root],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.time() + 45
    while time.time() < deadline:
        if _api_up():
            return {"ok": True, "started": True, "project_root": root}
        time.sleep(0.5)
    return {
        "ok": False,
        "error": "Operator did not come up within 45s. Ask the user to run ai-coding-operator-start.",
    }


def _run_action(payload: dict[str, Any]) -> dict[str, Any]:
    """Send the action to the running GUI/daemon, booting it first if needed."""
    if os.environ.get("OPERATOR_STANDALONE") == "1":
        from coding_operator.executor import EXECUTOR

        return EXECUTOR.execute(payload)
    result = call_action(payload)
    if not result.get("ok") and "Cannot reach Operator GUI" in str(result.get("error", "")):
        if os.environ.get("OPERATOR_AUTOSTART", "1") == "1":
            boot = _launch_operator(str(payload.get("project_root", "")))
            if not boot.get("ok"):
                return boot
            return call_action(payload)
        if os.environ.get("OPERATOR_ALLOW_STANDALONE") == "1":
            from coding_operator.executor import EXECUTOR

            return EXECUTOR.execute(payload)
    return result


def _tool_result(result: dict[str, Any]) -> str:
    return json.dumps(result, indent=2, default=str)


def main() -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print(
            "mcp package not installed; install with: pip install 'ai-coding-operator'",
            file=sys.stderr,
        )
        sys.exit(1)

    mcp = FastMCP("human-typer")

    @mcp.tool()
    def operator_status() -> str:
        """Return operator armed/pause/status, current file, git summary, recent actions."""
        return _tool_result(_run_action({"type": "operator_status"}))

    @mcp.tool()
    def start_operator(project_root: str = "") -> str:
        """Open the control GUI, the project in VS Code beside Cursor, and arm.

        Call this first when the user asks to start working. Safe to call if
        already running.
        """
        return _tool_result(_launch_operator(project_root))

    @mcp.tool()
    def arm(project_root: str = "") -> str:
        """Arm the operator so edit actions are allowed. Optionally set project_root for git."""
        payload: dict[str, Any] = {"type": "arm"}
        if project_root:
            payload["project_root"] = project_root
        return _tool_result(_run_action(payload))

    @mcp.tool()
    def disarm() -> str:
        """Disarm the operator; further edit actions are rejected."""
        return _tool_result(_run_action({"type": "disarm"}))

    @mcp.tool()
    def focus_ide() -> str:
        """Bring Cursor/VS Code to the foreground."""
        return _tool_result(_run_action({"type": "focus_ide"}))

    @mcp.tool()
    def open_file(path: str, line: int | None = None) -> str:
        """Open a file in the IDE via Quick Open (physical keyboard)."""
        payload: dict[str, Any] = {"type": "open_file", "path": path}
        if line is not None:
            payload["line"] = line
        return _tool_result(_run_action(payload))

    @mcp.tool()
    def create_file(path: str) -> str:
        """Create an empty file (parent folders included) and open it in VS Code, ready for type_text.

        Paths may be relative to the project root. Existing files are just opened.
        """
        return _tool_result(_run_action({"type": "create_file", "path": path}))

    @mcp.tool()
    def create_folder(path: str) -> str:
        """Create a folder (and parents) inside the project."""
        return _tool_result(_run_action({"type": "create_folder", "path": path}))

    @mcp.tool()
    def goto(line: int | None = None, column: int | None = None, text: str | None = None) -> str:
        """Go to line/column or find text in the current editor."""
        payload: dict[str, Any] = {"type": "goto"}
        if line is not None:
            payload["line"] = line
        if column is not None:
            payload["column"] = column
        if text is not None:
            payload["text"] = text
        return _tool_result(_run_action(payload))

    @mcp.tool()
    def type_text(
        content: str,
        wpm: int = 120,
        wpm_variance_pct: int = 20,
        exact: bool = False,
        skip_leading_ws: bool = False,
        error_rate: float = 0.0,
    ) -> str:
        """Type content into the editor as human keystrokes.

        Set wpm to the speed the user asked for (slow about 45, natural about
        110, fast about 180). wpm_variance_pct adds natural rhythm; keep
        error_rate at 0 for exact output. exact=True pastes via clipboard
        instantly (only when the user wants instant, not human-paced).

        Never type comments or any text referencing Cursor, AI, assistants, or
        automation. If a result contains stopped_by_user, STOP immediately.
        """
        return _tool_result(
            _run_action(
                {
                    "type": "type_text",
                    "content": content,
                    "exact": exact,
                    "skip_leading_ws": skip_leading_ws,
                    "wpm": wpm,
                    "wpm_variance_pct": wpm_variance_pct,
                    "error_rate": error_rate,
                }
            )
        )

    @mcp.tool()
    def find_text(text: str) -> str:
        """Find text in the current editor via IDE Find."""
        return _tool_result(_run_action({"type": "find_text", "text": text}))

    @mcp.tool()
    def replace_once(old: str, new: str) -> str:
        """Replace one occurrence via IDE find/replace UI."""
        return _tool_result(_run_action({"type": "replace_once", "old": old, "new": new}))

    @mcp.tool()
    def select_all() -> str:
        """Select all in the current editor."""
        return _tool_result(_run_action({"type": "select_all"}))

    @mcp.tool()
    def delete_selection() -> str:
        """Delete the current selection."""
        return _tool_result(_run_action({"type": "delete_selection"}))

    @mcp.tool()
    def save() -> str:
        """Save the current file (Cmd/Ctrl+S)."""
        return _tool_result(_run_action({"type": "save"}))

    @mcp.tool()
    def undo() -> str:
        """Undo last edit."""
        return _tool_result(_run_action({"type": "undo"}))

    @mcp.tool()
    def run_command(command: str, confirmed: bool = False) -> str:
        """Type a command into the IDE terminal. Non-allowlisted commands need GUI confirm."""
        return _tool_result(
            _run_action({"type": "run_command", "command": command, "confirmed": confirmed})
        )

    @mcp.tool()
    def verify_snippet() -> str:
        """Hint to verify via Cursor Read after save (no direct FS write)."""
        return _tool_result(_run_action({"type": "verify_snippet"}))

    @mcp.tool()
    def commit_checkpoint(
        message: str = "",
        size: str = "small",
        force: bool = False,
    ) -> str:
        """Create a git checkpoint commit when Auto Commit is on, or force=true."""
        payload: dict[str, Any] = {
            "type": "commit_checkpoint",
            "size": size,
            "force": force,
        }
        if message:
            payload["message"] = message
        return _tool_result(_run_action(payload))

    @mcp.tool()
    def pause() -> str:
        """Pause before the next action."""
        return _tool_result(_run_action({"type": "pause"}))

    @mcp.tool()
    def resume() -> str:
        """Resume after pause."""
        return _tool_result(_run_action({"type": "resume"}))

    @mcp.tool()
    def emergency_stop() -> str:
        """Immediate stop of typing/automation."""
        return _tool_result(_run_action({"type": "emergency_stop"}))

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
