#!/usr/bin/env bash
# Install Cursor integration into a target project.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:-}"
if [[ -z "$TARGET" ]]; then
  echo "Usage: $0 /path/to/target-project"
  exit 1
fi
TARGET="$(cd "$TARGET" && pwd)"
VENV_PY="$ROOT/.venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  VENV_PY="$(command -v python3)"
fi

mkdir -p "$TARGET/.cursor/hooks" "$TARGET/.cursor/rules"

cat > "$TARGET/.cursor/mcp.json" <<EOF
{
  "mcpServers": {
    "human-typer": {
      "command": "${VENV_PY}",
      "args": ["-m", "mcp_server.server"],
      "env": {
        "PYTHONPATH": "${ROOT}",
        "OPERATOR_URL": "http://127.0.0.1:8765"
      }
    }
  }
}
EOF

cp "$ROOT/cursor_integration/hooks.json.example" "$TARGET/.cursor/hooks.json"
cp "$ROOT/cursor_integration/hooks/"*.sh "$TARGET/.cursor/hooks/"
chmod +x "$TARGET/.cursor/hooks/"*.sh
cp "$ROOT/cursor_integration/rules/human-typer-only.mdc" "$TARGET/.cursor/rules/"

echo "Installed AI Coding Operator integration into $TARGET"
echo "1. Start GUI: $VENV_PY -m coding_operator.gui"
echo "2. Arm in GUI, open this project in Cursor Agent mode"
echo "3. Reload MCP servers in Cursor if needed"
