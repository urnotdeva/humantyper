#!/usr/bin/env bash
# Best-effort gate against shell filesystem mutations.
set -u
if [ -f "$HOME/.cursor/human-typer-off" ]; then
  printf '{ "permission": "allow" }\n'
  exit 0
fi
input=$(cat)
# Extract command field if present (jq optional)
command=""
if command -v jq >/dev/null 2>&1; then
  command=$(echo "$input" | jq -r '.command // .tool_input.command // empty' 2>/dev/null || true)
else
  command=$(echo "$input" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

lower=$(echo "$command" | tr '[:upper:]' '[:lower:]')

deny_patterns=(
  'rm -rf'
  'rm -fr'
  'git reset --hard'
  'git clean -fd'
  'git clean -f'
  ' sed -i'
  'sed -i '
  ' tee '
  ' >'
  ' >>'
  'python -c'
  'python3 -c'
  'node -e'
  'perl -i'
  'dd if='
)

word_cmds='(cp|mv|chmod|chown|truncate)'
if [[ "$lower" =~ (^|[[:space:]\;\&\|\(])${word_cmds}[[:space:]] ]]; then
  cat <<EOF
{
  "permission": "deny",
  "agent_message": "Shell mutation blocked. Use human-typer for edits, or ask the user to run this manually."
}
EOF
  exit 0
fi

for pat in "${deny_patterns[@]}"; do
  if [[ "$lower" == *"$pat"* ]]; then
    cat <<EOF
{
  "permission": "deny",
  "agent_message": "Shell mutation blocked. Use human-typer MCP for edits, or ask the user to run this manually."
}
EOF
    exit 0
  fi
done

# Allow read-only / common verify commands
cat <<'EOF'
{ "permission": "allow" }
EOF
exit 0
