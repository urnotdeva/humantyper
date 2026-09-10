#!/usr/bin/env bash
# Deny native Cursor file-edit tools; redirect agent to human-typer MCP.
set -euo pipefail
if [ -f "$HOME/.cursor/human-typer-off" ]; then
  printf '{ "permission": "allow" }\n'
  exit 0
fi
# Read stdin JSON (unused beyond triggering deny)
cat >/dev/null
cat <<'EOF'
{
  "permission": "deny",
  "agent_message": "Native file edits are disabled for AI Coding Operator. Use human-typer MCP tools only: arm, open_file, create_file, type_text, replace_once, save, run_command. Do not use Write, StrReplace, Delete, or Shell to mutate files."
}
EOF
exit 0
