# AI Coding Operator

Cursor is the **brain**. Human Typer is the **hands**.

This app does **not** write project files with Python `open()`. It drives the already-open Cursor/VS Code window with realistic keyboard/mouse automation, exposed to Cursor as an MCP server. Hooks deny native `Write`/`StrReplace` so the agent must use MCP tools.

## Architecture

```
User task (Cursor chat)
  → Cursor Agent (plan / Read / verify)
  → human-typer MCP tools
  → Executor + Human Typer
  → physical keystrokes in Cursor/VS Code
  → verify (Read / tests) → fix loop
  → Git checkpoints
```

## Install

```bash
cd /Users/deva/coding/auto
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

**macOS:** grant Accessibility permission to Terminal/Cursor/Python when prompted (System Settings → Privacy & Security → Accessibility).

**Linux:** X11 + `pynput`. Optional: `pip install -e ".[linux]"` for uinput.

## Run the control GUI (required while using MCP)

The GUI hosts the executor on `http://127.0.0.1:8765`. Cursor’s MCP process forwards every tool call to that API so Arm / Pause / Stop / command confirms stay in sync.

```bash
source .venv/bin/activate
ai-coding-operator
# or: python -m coding_operator.gui
```

1. Browse to your **project root**
2. Click **Arm**
3. Use **Pause / Stop / Esc** as needed
4. Toggle **Auto Commit** or press **Commit Now**
5. Leave the control process running while Cursor works

If your Python lacks Tk (`brew install python-tk` or use system Python), run the headless daemon instead:

```bash
ai-coding-operator-daemon /path/to/project
# Arms immediately and serves http://127.0.0.1:8765
```

Command confirmation for non-allowlisted `run_command` will time out unless you use the GUI or pass `confirmed=true` after explicit user approval in chat.

## Wire Cursor (MCP + hooks + rule)

Install into the **target project** (the folder you want Cursor to edit):

```bash
ai-coding-operator-install /path/to/your/project
# or: python cursor_integration/install.py /path/to/your/project
```

This writes, inside that project only:

- `.cursor/mcp.json` — the `human-typer` server entry (pointing at this repo's venv)
- `.cursor/hooks.json` + `.cursor/hooks/` — deny native edits and shell writes
- `.cursor/rules/human-typer-only.mdc` — the always-on rule

Existing entries in those files are preserved. Re-run any time to refresh. Remove with `--uninstall`.
Temporarily allow native edits on this machine with `touch ~/.cursor/human-typer-off` (delete the file to re-enable).

Stay in **Agent** mode (not Ask). Ask mode strips MCP.

## Typical Cursor flow

1. In Cursor: “Start working on this project: add authentication with tests”  
2. Agent calls `start_operator` → GUI opens, VS Code opens the project on the left, Cursor sits on the right, operator armed  
3. Agent calls `open_file` / `type_text` / `save` / `run_command`  
4. You see typing in the editor  
5. Agent Reads results and fixes via MCP  
6. `commit_checkpoint` or Commit Now  

## MCP tools

`operator_status`, `start_operator`, `arm`, `disarm`, `focus_ide`, `open_file`, `create_file`, `goto`, `type_text`, `find_text`, `replace_once`, `select_all`, `delete_selection`, `save`, `undo`, `run_command`, `verify_snippet`, `commit_checkpoint`, `pause`, `resume`, `emergency_stop`

## Tests

```bash
source .venv/bin/activate
pytest -q
```

## Packages

| Package | Role |
|---------|------|
| `human_typer` | TypingEngine, backends (macOS/Linux/uinput), typos, mouse path |
| `coding_operator` | Control state, action schema, VS Code nav, executor, git, GUI |
| `mcp_server` | stdio MCP for Cursor |
| `cursor_integration` | Example mcp.json, hooks, alwaysApply rule |

## Safety

- Esc and **Stop** always halt typing  
- Pause waits before the next action  
- Destructive / unknown `run_command`s need GUI confirmation  
- Hooks deny native edits and many shell write patterns (best-effort)  

## Note on package name

The Python package is `coding_operator` (not `operator`) so it does not shadow the stdlib `operator` module.

## Start everything (recommended)

```bash
ai-coding-operator-start /path/to/target/project
# or: python -m coding_operator.start /path/to/target/project
```

This opens the target project in VS Code, brings up Cursor, arranges them
side by side (VS Code left, Cursor right), and opens the control GUI in the
bottom-right corner, already armed and serving the control API on
`127.0.0.1:8765`.

Esc is monitored system-wide while the operator is active. Pressing it stops
the current typing instantly; the in-flight tool call returns
`"Typing stopped by user"` with `stopped_by_user: true`, and every further
typing call is refused until you press Resume or Arm in the GUI. The agent is
instructed to stop iterating as soon as it sees that result.

Typing speed is set per call by the agent (`wpm`, `wpm_variance_pct`) based on
what you ask for; output is exact (`error_rate` 0). Comment lines that would
reveal automation are dropped before they are typed, and the always-on rule
forbids comments and any reference to automation in the code.

## Safety and fidelity

- Typing only happens while VS Code is the active window. Switch to another
  app and the operator pauses within one keystroke; switch back and it resumes.
  The `type_text` result reports `focus_interruptions` so the agent re-verifies
  the file.
- The installer writes typing-safe workspace settings to `.vscode/settings.json`
  (auto-indent, auto-closing pairs, suggestions and Copilot off) so the typed
  text lands exactly as sent. The engine also resets editor indentation after
  every Enter as a second guard.
- `create_file` / `create_folder` create the entry on disk and open it in
  VS Code; content is then typed by keystrokes like everything else.
- Logs: `~/.ai-coding-operator/operator.log` (actions) and `crash.log`
  (native crash traces). Run `ai-coding-operator-doctor /path/to/project` to
  check a machine and project before starting.
# humantyper
