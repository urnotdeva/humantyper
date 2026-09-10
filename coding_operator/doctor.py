"""Check that a project and this machine are ready for the operator."""

from __future__ import annotations

import importlib
import json
import os
import platform
import shutil
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _ok(label: str, good: bool, hint: str = "") -> bool:
    mark = "ok  " if good else "FAIL"
    line = f"[{mark}] {label}"
    if not good and hint:
        line += f"\n       {hint}"
    print(line)
    return good


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _accessibility_trusted() -> bool | None:
    if platform.system() != "Darwin":
        return None
    import ctypes
    import ctypes.util

    lib = ctypes.CDLL(ctypes.util.find_library("ApplicationServices"))
    lib.AXIsProcessTrusted.restype = ctypes.c_bool
    return bool(lib.AXIsProcessTrusted())


def main() -> None:
    args = sys.argv[1:]
    project = Path(args[0]).expanduser().resolve() if args else Path.cwd()
    good = True

    print(f"operator repo: {ROOT}")
    print(f"project:       {project}")
    print()

    venv = ROOT / ".venv" / "bin" / "python"
    good &= _ok("venv python present", venv.exists(), "run: python3 -m venv .venv && .venv/bin/pip install -e .")
    for mod in ("mcp", "pynput"):
        try:
            importlib.import_module(mod)
            good &= _ok(f"module {mod} importable", True)
        except Exception as exc:
            good &= _ok(f"module {mod} importable", False, str(exc))

    if platform.system() == "Darwin":
        good &= _ok("Visual Studio Code installed", Path("/Applications/Visual Studio Code.app").exists(), "install VS Code")
        trusted = _accessibility_trusted()
        _ok(
            "Accessibility granted to this launcher",
            bool(trusted),
            "System Settings -> Privacy & Security -> Accessibility: enable the app that launches the operator (Cursor and/or your terminal)",
        )
    else:
        good &= _ok("code on PATH", shutil.which("code") is not None, "install VS Code and its CLI")
        _ok("xdotool present (focus guard)", shutil.which("xdotool") is not None, "sudo apt install xdotool")
        _ok("wmctrl present (window layout)", shutil.which("wmctrl") is not None, "sudo apt install wmctrl")

    cursor_dir = project / ".cursor"
    mcp_path = cursor_dir / "mcp.json"
    servers = {}
    if mcp_path.exists():
        try:
            servers = json.loads(mcp_path.read_text()).get("mcpServers", {})
        except json.JSONDecodeError:
            pass
    entry = servers.get("human-typer")
    good &= _ok(".cursor/mcp.json has human-typer", entry is not None, f"run: ai-coding-operator-install {project}")
    if entry:
        good &= _ok("  server command exists", Path(entry.get("command", "")).exists(), "re-run the installer")
        good &= _ok("  PYTHONPATH points at operator repo", entry.get("env", {}).get("PYTHONPATH") == str(ROOT), "re-run the installer")
        _ok("  OPERATOR_PROJECT matches project", entry.get("env", {}).get("OPERATOR_PROJECT") == str(project), "re-run the installer")

    hooks_json = cursor_dir / "hooks.json"
    good &= _ok(".cursor/hooks.json present", hooks_json.exists(), "re-run the installer")
    for name in ("deny-native-edits.sh", "deny-shell-writes.sh"):
        script = cursor_dir / "hooks" / name
        good &= _ok(f"  {name} executable", script.exists() and os.access(script, os.X_OK), "re-run the installer")
    good &= _ok(".cursor/rules/human-typer-only.mdc present", (cursor_dir / "rules" / "human-typer-only.mdc").exists(), "re-run the installer")
    settings = project / ".vscode" / "settings.json"
    typing_safe = False
    if settings.exists():
        try:
            typing_safe = json.loads(settings.read_text()).get("editor.autoIndent") == "none"
        except json.JSONDecodeError:
            typing_safe = False
    good &= _ok(".vscode/settings.json typing-safe", typing_safe, "re-run the installer")

    off = Path.home() / ".cursor" / "human-typer-off"
    _ok("off switch not active", not off.exists(), f"delete {off} to re-enable the hooks")
    running = _port_open(8765)
    _ok("operator running on 127.0.0.1:8765", running, "not running yet: the agent starts it with start_operator, or run ai-coding-operator-start")

    print()
    print("ready" if good else "fix the FAIL items above, then re-run")
    print("In Cursor: open this folder, enable the human-typer server when prompted (Settings -> MCP), use Agent mode.")


if __name__ == "__main__":
    main()
