"""Install the Cursor integration into one project folder."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "cursor_integration"
SERVER_NAME = "human-typer"
HOOK_FILES = ("deny-native-edits.sh", "deny-shell-writes.sh")
RULE_FILE = "human-typer-only.mdc"
VSCODE_SETTINGS = {
    "editor.autoIndent": "none",
    "editor.autoClosingBrackets": "never",
    "editor.autoClosingQuotes": "never",
    "editor.autoClosingDelete": "never",
    "editor.autoSurround": "never",
    "editor.autoIndentOnPaste": False,
    "editor.formatOnType": False,
    "editor.formatOnSave": False,
    "editor.formatOnPaste": False,
    "editor.quickSuggestions": {"other": False, "comments": False, "strings": False},
    "editor.suggestOnTriggerCharacters": False,
    "editor.acceptSuggestionOnEnter": "off",
    "editor.acceptSuggestionOnCommitCharacter": False,
    "editor.inlineSuggest.enabled": False,
    "editor.tabCompletion": "off",
    "editor.snippetSuggestions": "none",
    "editor.wordBasedSuggestions": "off",
    "editor.parameterHints.enabled": False,
    "editor.linkedEditing": False,
    "editor.trimAutoWhitespace": False,
    "files.trimTrailingWhitespace": False,
    "files.insertFinalNewline": False,
    "emmet.triggerExpansionOnTab": False,
    "github.copilot.enable": {"*": False},
}
LANGUAGES = (
    "python", "javascript", "typescript", "javascriptreact", "typescriptreact",
    "json", "jsonc", "html", "css", "scss", "markdown", "yaml", "shellscript",
    "go", "rust", "java", "c", "cpp", "csharp", "ruby", "php", "swift", "kotlin", "sql",
)
LANGUAGE_KEYS = (
    "editor.autoIndent",
    "editor.autoClosingBrackets",
    "editor.autoClosingQuotes",
    "editor.autoSurround",
    "editor.formatOnType",
    "editor.formatOnSave",
    "editor.quickSuggestions",
    "editor.suggestOnTriggerCharacters",
    "editor.acceptSuggestionOnEnter",
    "editor.inlineSuggest.enabled",
    "editor.wordBasedSuggestions",
)
for _lang in LANGUAGES:
    VSCODE_SETTINGS[f"[{_lang}]"] = {key: VSCODE_SETTINGS[key] for key in LANGUAGE_KEYS}


def _python() -> str:
    venv = ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text() or "{}")
    except json.JSONDecodeError:
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copyfile(path, backup)
        print(f"warning: {path} was not valid JSON; backed up to {backup}")
        return {}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def install(project: Path) -> None:
    cursor_dir = project / ".cursor"
    cursor_dir.mkdir(parents=True, exist_ok=True)

    path = cursor_dir / "mcp.json"
    data = _load_json(path)
    data.setdefault("mcpServers", {})[SERVER_NAME] = {
        "command": _python(),
        "args": ["-m", "mcp_server.server"],
        "env": {
            "PYTHONPATH": str(ROOT),
            "OPERATOR_URL": "http://127.0.0.1:8765",
            "OPERATOR_PROJECT": str(project),
            "OPERATOR_IDE": "Visual Studio Code",
        },
    }
    _save_json(path, data)
    print(f"server  {path}")

    hooks_dir = cursor_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    for name in HOOK_FILES:
        dst = hooks_dir / name
        shutil.copyfile(PACK / "hooks" / name, dst)
        os.chmod(dst, 0o755)
    path = cursor_dir / "hooks.json"
    data = _load_json(path)
    data.setdefault("version", 1)
    hooks = data.setdefault("hooks", {})
    wanted = {
        "preToolUse": {
            "matcher": "Write|StrReplace|Delete|EditNotebook|ApplyPatch",
            "command": ".cursor/hooks/deny-native-edits.sh",
            "failClosed": True,
        },
        "beforeShellExecution": {
            "command": ".cursor/hooks/deny-shell-writes.sh",
            "failClosed": True,
        },
    }
    for event, entry in wanted.items():
        entries = hooks.setdefault(event, [])
        entries[:] = [e for e in entries if e.get("command") != entry["command"]]
        entries.append(entry)
    _save_json(path, data)
    print(f"hooks   {path}")

    rules_dir = cursor_dir / "rules"
    rules_dir.mkdir(exist_ok=True)
    dst = rules_dir / RULE_FILE
    shutil.copyfile(PACK / "rules" / RULE_FILE, dst)
    print(f"rule    {dst}")

    path = project / ".vscode" / "settings.json"
    data = _load_json(path)
    data.update(VSCODE_SETTINGS)
    _save_json(path, data)
    print(f"vscode  {path}")


def uninstall(project: Path) -> None:
    cursor_dir = project / ".cursor"
    path = cursor_dir / "mcp.json"
    data = _load_json(path)
    if data.get("mcpServers", {}).pop(SERVER_NAME, None) is not None:
        _save_json(path, data)
    path = cursor_dir / "hooks.json"
    if path.exists():
        data = _load_json(path)
        hooks = data.get("hooks", {})
        for event in list(hooks):
            hooks[event] = [
                e
                for e in hooks[event]
                if not any(name in e.get("command", "") for name in HOOK_FILES)
            ]
            if not hooks[event]:
                del hooks[event]
        _save_json(path, data)
    for name in HOOK_FILES:
        (cursor_dir / "hooks" / name).unlink(missing_ok=True)
    (cursor_dir / "rules" / RULE_FILE).unlink(missing_ok=True)
    path = project / ".vscode" / "settings.json"
    if path.exists():
        data = _load_json(path)
        for key in VSCODE_SETTINGS:
            data.pop(key, None)
        _save_json(path, data)
    print(f"removed human-typer integration from {project}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", nargs="?", default=".", help="project folder (default: current directory)")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()
    project = Path(args.project).expanduser().resolve()
    if not project.is_dir():
        sys.exit(f"not a directory: {project}")
    if args.uninstall:
        uninstall(project)
        return
    install(project)
    print()
    print(f"Done. Open {project} in Cursor; the rule, hooks and server are active there.")
    print(f"Off switch for this machine: create {Path.home() / '.cursor' / 'human-typer-off'} (delete it to re-enable).")


if __name__ == "__main__":
    main()
