#!/usr/bin/env bash
# codex-jp-harness installer (macOS / Linux / Git Bash on Windows)
#
# Mirrors scripts/install.ps1 for POSIX-like shells.
# Usage:
#   bash scripts/install.sh                      # register MCP and place skill
#   bash scripts/install.sh --append-agents-rule # also append quality-gate rule to AGENTS.md
#   bash scripts/install.sh --skip-skill         # do not place the skill file

set -euo pipefail

APPEND_AGENTS_RULE=false
FORCE=false
SKIP_SKILL=false
ENABLE_HOOKS=false
FORCE_HOOKS=false
for arg in "$@"; do
  case "$arg" in
    --append-agents-rule) APPEND_AGENTS_RULE=true ;;
    --force)              FORCE=true ;;
    --skip-skill)         SKIP_SKILL=true ;;
    --enable-hooks)       ENABLE_HOOKS=true ;;
    --force-hooks)        FORCE_HOOKS=true ;;
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
SKILL_SRC="$REPO_ROOT/skills/jp-harness-tune/SKILL.md"
SKILL_DEST_DIR="$CODEX_DIR/skills/jp-harness-tune"
SKILL_DEST_PATH="$SKILL_DEST_DIR/SKILL.md"
HOOKS_JSON_PATH="$CODEX_DIR/hooks.json"
HOOKS_TEMPLATE="$REPO_ROOT/config/hooks.example.json"
STOP_HOOK_PATH="$REPO_ROOT/hooks/stop-finalize-check.sh"
START_HOOK_PATH="$REPO_ROOT/hooks/session-start-reeducate.sh"

# Preflight
if [[ ! -d "$CODEX_DIR" ]]; then
  echo "[codex-jp-harness] Codex directory not found at $CODEX_DIR. Is Codex CLI or Codex App installed?" >&2
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
if [[ "$SKIP_SKILL" != "true" && ! -f "$SKILL_SRC" ]]; then
  echo "[codex-jp-harness] SKILL.md not found at $SKILL_SRC. Re-clone the repo or pass --skip-skill to bypass." >&2
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

# Skill placement
# Hash helper: pick the first available SHA-256 command and print "HASH filename".
# Falls back through sha256sum (GNU), shasum -a 256 (macOS / BSD), certutil (Git Bash on Windows).
sha256_of() {
  local path="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$path" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$path" | awk '{print $1}'
  elif command -v certutil >/dev/null 2>&1; then
    certutil -hashfile "$path" SHA256 2>/dev/null | sed -n '2p' | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]'
  else
    echo ""
  fi
}

if [[ "$SKIP_SKILL" == "true" ]]; then
  echo "[codex-jp-harness] Skipping skill placement (--skip-skill)."
else
  mkdir -p "$SKILL_DEST_DIR"
  if [[ ! -f "$SKILL_DEST_PATH" ]]; then
    cp -f "$SKILL_SRC" "$SKILL_DEST_PATH"
    echo "[codex-jp-harness] Installed skill: $SKILL_DEST_PATH"
  else
    src_hash="$(sha256_of "$SKILL_SRC")"
    dest_hash="$(sha256_of "$SKILL_DEST_PATH")"
    if [[ -z "$src_hash" || -z "$dest_hash" ]]; then
      echo "[codex-jp-harness] No SHA-256 tool found; skipping skill overwrite to be safe at $SKILL_DEST_PATH" >&2
    elif [[ "$src_hash" == "$dest_hash" ]]; then
      echo "[codex-jp-harness] Skill up to date: $SKILL_DEST_PATH"
    else
      echo "[codex-jp-harness] Existing SKILL.md at $SKILL_DEST_PATH differs from the bundled version. Skip overwrite to preserve your edits. Remove the file manually and re-run to reinstall." >&2
    fi
  fi
fi

# Hooks placement (opt-in, experimental, Codex 0.120.0+)
if [[ "$ENABLE_HOOKS" == "true" ]]; then
  echo ""
  echo "[codex-jp-harness] --enable-hooks: configuring Stop + SessionStart hooks (experimental)."

  codex_version_ok=false
  if command -v codex >/dev/null 2>&1; then
    version_str="$(codex --version 2>/dev/null || true)"
    echo "[codex-jp-harness] Detected Codex version: $version_str"
    if [[ "$version_str" =~ ([0-9]+)\.([0-9]+)\.([0-9]+) ]]; then
      major="${BASH_REMATCH[1]}"
      minor="${BASH_REMATCH[2]}"
      if [[ "$major" -gt 0 ]] || { [[ "$major" -eq 0 ]] && [[ "$minor" -ge 120 ]]; }; then
        codex_version_ok=true
      fi
    fi
  fi

  if [[ "$codex_version_ok" != "true" ]]; then
    echo "[codex-jp-harness] Codex 0.120.0 or later (CLI or App) is required for hooks. Skipping hooks setup." >&2
  elif [[ ! -f "$STOP_HOOK_PATH" || ! -f "$START_HOOK_PATH" || ! -f "$HOOKS_TEMPLATE" ]]; then
    echo "[codex-jp-harness] Hooks source files missing in repo. Skipping hooks setup." >&2
  else
    # Ensure codex_hooks = true in config.toml (idempotent)
    if grep -qE '^[[:space:]]*codex_hooks[[:space:]]*=[[:space:]]*true\b' "$CONFIG_PATH"; then
      echo "[codex-jp-harness] codex_hooks = true already set in config.toml."
    else
      if [[ -n "$(tail -c1 "$CONFIG_PATH")" ]]; then
        printf '\n' >> "$CONFIG_PATH"
      fi
      printf 'codex_hooks = true\n' >> "$CONFIG_PATH"
      echo "[codex-jp-harness] Set codex_hooks = true in config.toml."
    fi

    # Build absolute commands
    stop_cmd="bash \"$STOP_HOOK_PATH\""
    start_cmd="bash \"$START_HOOK_PATH\""
    # JSON-escape backslashes and double quotes
    stop_cmd_json="$(printf '%s' "$stop_cmd" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read())[1:-1])' 2>/dev/null || printf '%s' "$stop_cmd" | sed 's/\\/\\\\/g; s/"/\\"/g')"
    start_cmd_json="$(printf '%s' "$start_cmd" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read())[1:-1])' 2>/dev/null || printf '%s' "$start_cmd" | sed 's/\\/\\\\/g; s/"/\\"/g')"

    rendered="$(python3 - "$HOOKS_TEMPLATE" "$stop_cmd_json" "$start_cmd_json" <<'PY' 2>/dev/null || true
import sys, pathlib
path, stop_cmd, start_cmd = sys.argv[1], sys.argv[2], sys.argv[3]
tpl = pathlib.Path(path).read_text(encoding="utf-8")
sys.stdout.write(tpl.replace("{{STOP_COMMAND}}", stop_cmd).replace("{{SESSION_START_COMMAND}}", start_cmd))
PY
)"
    if [[ -z "$rendered" ]]; then
      echo "[codex-jp-harness] Failed to render hooks.json template (python3 required)." >&2
    elif [[ -f "$HOOKS_JSON_PATH" ]]; then
      existing="$(cat "$HOOKS_JSON_PATH")"
      if [[ "$(printf '%s' "$existing" | tr -d '[:space:]')" == "$(printf '%s' "$rendered" | tr -d '[:space:]')" ]]; then
        echo "[codex-jp-harness] hooks.json already up to date."
      elif [[ "$FORCE_HOOKS" == "true" ]]; then
        printf '%s' "$rendered" > "$HOOKS_JSON_PATH"
        echo "[codex-jp-harness] Overwrote existing hooks.json (--force-hooks)."
      else
        echo "[codex-jp-harness] Existing hooks.json at $HOOKS_JSON_PATH differs from bundled template." >&2
        echo "[codex-jp-harness] Review and re-run with --force-hooks to overwrite, or merge manually." >&2
        echo "[codex-jp-harness] Bundled template path: $HOOKS_TEMPLATE" >&2
      fi
    else
      printf '%s' "$rendered" > "$HOOKS_JSON_PATH"
      echo "[codex-jp-harness] Wrote $HOOKS_JSON_PATH"
    fi
  fi
fi

echo ""
echo "[codex-jp-harness] Installation complete."
echo "[codex-jp-harness] Restart Codex (CLI or App) to activate the MCP server and the jp-harness-tune skill."
if [[ "$ENABLE_HOOKS" == "true" ]]; then
  echo "[codex-jp-harness] Hooks (experimental) require Codex 0.120.0+ (CLI or App). See docs/HOOKS.md for details."
fi
