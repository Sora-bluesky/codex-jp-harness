#!/usr/bin/env bash
# codex-jp-harness installer (macOS / Linux / Git Bash on Windows)
#
# Mirrors scripts/install.ps1 for POSIX-like shells.
# Usage:
#   bash scripts/install.sh                      # register MCP only
#   bash scripts/install.sh --append-agents-rule # also append 7.p to AGENTS.md

set -euo pipefail

APPEND_AGENTS_RULE=false
FORCE=false
for arg in "$@"; do
  case "$arg" in
    --append-agents-rule) APPEND_AGENTS_RULE=true ;;
    --force)              FORCE=true ;;
    *) echo "Unknown argument: $arg" >&2; exit 1 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# venv python: Unix layout first, Windows fallback for Git Bash on Windows
VENV_PYTHON="$REPO_ROOT/.venv/bin/python"
if [[ ! -f "$VENV_PYTHON" && -f "$REPO_ROOT/.venv/Scripts/python.exe" ]]; then
  VENV_PYTHON="$REPO_ROOT/.venv/Scripts/python.exe"
fi

# On Git Bash / MSYS, convert to native Windows path so Codex (non-MSYS) can
# spawn python directly without depending on the bash path translation layer.
if command -v cygpath >/dev/null 2>&1 && [[ "$VENV_PYTHON" =~ \.exe$ ]]; then
  VENV_PYTHON="$(cygpath -w "$VENV_PYTHON")"
fi

CODEX_DIR="$HOME/.codex"
CONFIG_PATH="$CODEX_DIR/config.toml"
AGENTS_PATH="$CODEX_DIR/AGENTS.md"
RULE_BLOCK_PATH="$REPO_ROOT/config/agents_rule.md"

# Preflight
if [[ ! -d "$CODEX_DIR" ]]; then
  echo "[codex-jp-harness] Codex directory not found at $CODEX_DIR. Is Codex CLI installed?" >&2
  exit 1
fi
if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "[codex-jp-harness] Codex config.toml not found at $CONFIG_PATH" >&2
  exit 1
fi
if [[ ! -f "$VENV_PYTHON" ]]; then
  echo "[codex-jp-harness] .venv Python not found. Run 'uv sync' in $REPO_ROOT first." >&2
  exit 1
fi

# Remove any existing [mcp_servers.jp_lint] entry (idempotent re-install)
if grep -q '^\[mcp_servers\.jp_lint\]' "$CONFIG_PATH"; then
  if [[ "$FORCE" != "true" ]]; then
    echo "[codex-jp-harness] [mcp_servers.jp_lint] already present. Rewriting to match current repo location."
  fi
  tmp="$(mktemp)"
  awk '
    /^\[mcp_servers\.jp_lint\][[:space:]]*$/ { skip = 1; next }
    /^\[[^]]+\][[:space:]]*$/                { skip = 0 }
    !skip { print }
  ' "$CONFIG_PATH" > "$tmp"
  # Trim trailing whitespace from end of file
  printf '%s\n' "$(cat "$tmp")" > "$CONFIG_PATH"
  rm -f "$tmp"
fi

# Register MCP server entry. Backslashes in paths are TOML-escaped.
python_path_escaped="${VENV_PYTHON//\\/\\\\}"
{
  echo ""
  echo "[mcp_servers.jp_lint]"
  echo "command = \"${python_path_escaped}\""
  echo 'args = ["-m", "codex_jp_harness.server"]'
} >> "$CONFIG_PATH"
echo "[codex-jp-harness] Registered [mcp_servers.jp_lint] with venv Python: $VENV_PYTHON"

# AGENTS.md rule handling
if [[ -f "$AGENTS_PATH" ]]; then
  if grep -q 'mcp__jp_lint__finalize' "$AGENTS_PATH"; then
    echo "[codex-jp-harness] AGENTS.md already references finalize rule. OK."
  elif [[ "$APPEND_AGENTS_RULE" == "true" ]]; then
    if [[ ! -f "$RULE_BLOCK_PATH" ]]; then
      echo "[codex-jp-harness] agents_rule.md not found at $RULE_BLOCK_PATH" >&2
      exit 1
    fi
    # Strip HTML comment block
    rule_stripped="$(awk '/<!--/,/-->/{next} {print}' "$RULE_BLOCK_PATH")"
    # Ensure AGENTS.md ends with a newline before appending
    if [[ -n "$(tail -c1 "$AGENTS_PATH")" ]]; then
      printf '\n' >> "$AGENTS_PATH"
    fi
    printf '%s\n' "$rule_stripped" >> "$AGENTS_PATH"
    echo "[codex-jp-harness] Appended finalize rule block to AGENTS.md"
  else
    echo ""
    echo "[codex-jp-harness] AGENTS.md does not yet reference the finalize rule."
    echo "[codex-jp-harness] Re-run with --append-agents-rule to append automatically,"
    echo "[codex-jp-harness] or manually append the content of config/agents_rule.md."
  fi
else
  echo "[codex-jp-harness] AGENTS.md not found; skipping rule handling."
fi

echo ""
echo "[codex-jp-harness] Installation complete."
echo "[codex-jp-harness] Restart Codex CLI to activate the MCP server."
