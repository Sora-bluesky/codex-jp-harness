#!/usr/bin/env bash
# codex-jp-harness uninstaller (macOS / Linux / Git Bash on Windows)
#
# Removes the [mcp_servers.jp_lint] entry from ~/.codex/config.toml.
# AGENTS.md edits are NOT automatic — we print a manual removal notice.

set -euo pipefail

CODEX_DIR="$HOME/.codex"
CONFIG_PATH="$CODEX_DIR/config.toml"

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "[codex-jp-harness] Codex config.toml not found at $CONFIG_PATH" >&2
  exit 1
fi

if ! grep -q '^\[mcp_servers\.jp_lint\]' "$CONFIG_PATH"; then
  echo "[codex-jp-harness] [mcp_servers.jp_lint] not found; nothing to remove."
else
  backup="${CONFIG_PATH}.bak"
  cp "$CONFIG_PATH" "$backup"
  tmp="$(mktemp)"
  awk '
    /^\[mcp_servers\.jp_lint\][[:space:]]*$/ { skip = 1; next }
    /^\[[^]]+\][[:space:]]*$/                { skip = 0 }
    !skip { print }
  ' "$CONFIG_PATH" > "$tmp"
  printf '%s\n' "$(cat "$tmp")" > "$CONFIG_PATH"
  rm -f "$tmp"
  echo "[codex-jp-harness] Removed [mcp_servers.jp_lint] from config.toml"
  echo "[codex-jp-harness] Backup saved to $backup"
fi

echo ""
echo "[codex-jp-harness] Manual step required:"
echo "[codex-jp-harness]   1. Edit ~/.codex/AGENTS.md and remove the quality-gate rule block."
echo "[codex-jp-harness]   2. Restart Codex CLI."
