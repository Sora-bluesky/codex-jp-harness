#!/usr/bin/env bash
# ja-output-harness installer (macOS / Linux / Git Bash on Windows)
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
MODE=""
for arg in "$@"; do
  case "$arg" in
    --append-agents-rule) APPEND_AGENTS_RULE=true ;;
    --force)              FORCE=true ;;
    --skip-skill)         SKIP_SKILL=true ;;
    --enable-hooks)       ENABLE_HOOKS=true ;;
    --force-hooks)        FORCE_HOOKS=true ;;
    --mode=*)             MODE="${arg#--mode=}" ;;
    --mode)               echo "[ja-output-harness] --mode requires =value (e.g. --mode=lite)" >&2; exit 1 ;;
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
SKILL_SRC="$REPO_ROOT/skills/jp-harness-tune/SKILL.md"
SKILL_DEST_DIR="$CODEX_DIR/skills/jp-harness-tune"
SKILL_DEST_PATH="$SKILL_DEST_DIR/SKILL.md"
HOOKS_JSON_PATH="$CODEX_DIR/hooks.json"
HOOKS_TEMPLATE="$REPO_ROOT/config/hooks.example.json"
STOP_HOOK_PATH="$REPO_ROOT/hooks/stop-finalize-check.sh"
START_HOOK_PATH="$REPO_ROOT/hooks/session-start-reeducate.sh"
STATE_DIR="$CODEX_DIR/state"
MODE_MARKER="$STATE_DIR/jp-harness-mode"

# Mode resolution: explicit flag > marker file > "lite" (new install default).
if [[ -z "$MODE" && -f "$MODE_MARKER" ]]; then
  MODE="$(tr -d '[:space:]' < "$MODE_MARKER")"
fi
if [[ -z "$MODE" ]]; then
  MODE="lite"
fi
case "$MODE" in
  lite|strict-lite|strict) ;;
  *) echo "[ja-output-harness] Invalid --mode=$MODE (expected lite, strict-lite, strict)." >&2; exit 1 ;;
esac
echo "[ja-output-harness] Mode: $MODE"

if [[ "$MODE" == "strict" ]]; then
  RULE_BLOCK_PATH="$REPO_ROOT/config/agents_rule.md"
  RULE_MARKER='mcp__jp_lint__finalize'
else
  RULE_BLOCK_PATH="$REPO_ROOT/config/agents_rule_lite.md"
  RULE_MARKER='ja-output-harness lite'
fi

# lite / strict-lite require hooks (the Stop hook does the lint work).
if [[ "$MODE" != "strict" && "$ENABLE_HOOKS" != "true" ]]; then
  echo "[ja-output-harness] Mode '$MODE' requires hooks. Enabling."
  ENABLE_HOOKS=true
fi

# Preflight
if [[ ! -d "$CODEX_DIR" ]]; then
  echo "[ja-output-harness] Codex directory not found at $CODEX_DIR. Is Codex CLI or Codex App installed?" >&2
  exit 1
fi
if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "[ja-output-harness] Codex config.toml not found at $CONFIG_PATH" >&2
  exit 1
fi
if [[ ! -f "$VENV_PYTHON" ]]; then
  echo "[ja-output-harness] .venv Python not found. Run 'uv sync' in $REPO_ROOT first." >&2
  exit 1
fi
if [[ "$SKIP_SKILL" != "true" && ! -f "$SKILL_SRC" ]]; then
  echo "[ja-output-harness] SKILL.md not found at $SKILL_SRC. Re-clone the repo or pass --skip-skill to bypass." >&2
  exit 1
fi

# Remove any existing [mcp_servers.jp_lint] entry (idempotent re-install)
if grep -q '^\[mcp_servers\.jp_lint\]' "$CONFIG_PATH"; then
  if [[ "$FORCE" != "true" ]]; then
    echo "[ja-output-harness] [mcp_servers.jp_lint] already present. Rewriting to match current repo location."
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

if [[ "$MODE" == "strict" ]]; then
  # Register MCP server entry. Backslashes in paths are TOML-escaped.
  python_path_escaped="${VENV_PYTHON//\\/\\\\}"
  {
    echo ""
    echo "[mcp_servers.jp_lint]"
    echo "command = \"${python_path_escaped}\""
    echo 'args = ["-m", "ja_output_harness.server"]'
  } >> "$CONFIG_PATH"
  echo "[ja-output-harness] Registered [mcp_servers.jp_lint] (strict mode) with venv Python: $VENV_PYTHON"
else
  echo "[ja-output-harness] Skipped [mcp_servers.jp_lint] registration (mode=$MODE — local lint only)."
fi

# Write the mode marker so the Stop hook can branch on it at runtime.
mkdir -p "$STATE_DIR"
printf '%s' "$MODE" > "$MODE_MARKER"
echo "[ja-output-harness] Wrote mode marker: $MODE_MARKER = $MODE"

# AGENTS.md rule handling
if [[ -f "$AGENTS_PATH" ]]; then
  if grep -qF "$RULE_MARKER" "$AGENTS_PATH"; then
    echo "[ja-output-harness] AGENTS.md already contains the $MODE-mode rule. OK."
  elif [[ "$APPEND_AGENTS_RULE" == "true" ]]; then
    if [[ ! -f "$RULE_BLOCK_PATH" ]]; then
      echo "[ja-output-harness] agents_rule.md not found at $RULE_BLOCK_PATH" >&2
      exit 1
    fi
    # Strip HTML comment block
    rule_stripped="$(awk '/<!--/,/-->/{next} {print}' "$RULE_BLOCK_PATH")"
    # Ensure AGENTS.md ends with a newline before appending
    if [[ -n "$(tail -c1 "$AGENTS_PATH")" ]]; then
      printf '\n' >> "$AGENTS_PATH"
    fi
    printf '%s\n' "$rule_stripped" >> "$AGENTS_PATH"
    echo "[ja-output-harness] Appended finalize rule block to AGENTS.md"
  else
    echo ""
    echo "[ja-output-harness] AGENTS.md does not yet reference the finalize rule."
    echo "[ja-output-harness] Re-run with --append-agents-rule to append automatically,"
    echo "[ja-output-harness] or manually append the content of config/agents_rule.md."
  fi
else
  echo "[ja-output-harness] AGENTS.md not found; skipping rule handling."
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
  echo "[ja-output-harness] Skipping skill placement (--skip-skill)."
else
  mkdir -p "$SKILL_DEST_DIR"
  if [[ ! -f "$SKILL_DEST_PATH" ]]; then
    cp -f "$SKILL_SRC" "$SKILL_DEST_PATH"
    echo "[ja-output-harness] Installed skill: $SKILL_DEST_PATH"
  else
    src_hash="$(sha256_of "$SKILL_SRC")"
    dest_hash="$(sha256_of "$SKILL_DEST_PATH")"
    if [[ -z "$src_hash" || -z "$dest_hash" ]]; then
      echo "[ja-output-harness] No SHA-256 tool found; skipping skill overwrite to be safe at $SKILL_DEST_PATH" >&2
    elif [[ "$src_hash" == "$dest_hash" ]]; then
      echo "[ja-output-harness] Skill up to date: $SKILL_DEST_PATH"
    else
      echo "[ja-output-harness] Existing SKILL.md at $SKILL_DEST_PATH differs from the bundled version. Skip overwrite to preserve your edits. Remove the file manually and re-run to reinstall." >&2
    fi
  fi
fi

# Resolve a Python 3.8+ interpreter for hook-setup helpers. Git Bash on
# Windows often only ships `py` (Windows launcher), not `python3`, so we use
# the same probe that the hook scripts themselves use. Fall back to the
# repo's venv Python as a last resort (guaranteed to exist from preflight).
resolve_python3() {
  for cand in python3 python py; do
    if command -v "$cand" >/dev/null 2>&1; then
      if "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1; then
        printf '%s' "$cand"
        return 0
      fi
    fi
  done
  printf '%s' "$VENV_PYTHON"
}

# Hooks placement (opt-in, experimental, Codex 0.120.0+)
if [[ "$ENABLE_HOOKS" == "true" ]]; then
  echo ""
  echo "[ja-output-harness] --enable-hooks: configuring Stop + SessionStart hooks (experimental)."

  codex_version_ok=false
  if command -v codex >/dev/null 2>&1; then
    version_str="$(codex --version 2>/dev/null || true)"
    echo "[ja-output-harness] Detected Codex version: $version_str"
    if [[ "$version_str" =~ ([0-9]+)\.([0-9]+)\.([0-9]+) ]]; then
      major="${BASH_REMATCH[1]}"
      minor="${BASH_REMATCH[2]}"
      if [[ "$major" -gt 0 ]] || { [[ "$major" -eq 0 ]] && [[ "$minor" -ge 120 ]]; }; then
        codex_version_ok=true
      fi
    fi
  fi

  if [[ "$codex_version_ok" != "true" ]]; then
    echo "[ja-output-harness] Codex 0.120.0 or later (CLI or App) is required for hooks. Skipping hooks setup." >&2
  elif [[ ! -f "$STOP_HOOK_PATH" || ! -f "$START_HOOK_PATH" || ! -f "$HOOKS_TEMPLATE" ]]; then
    echo "[ja-output-harness] Hooks source files missing in repo. Skipping hooks setup." >&2
  else
    # Ensure codex_hooks = true in config.toml (idempotent)
    if grep -qE '^[[:space:]]*codex_hooks[[:space:]]*=[[:space:]]*true\b' "$CONFIG_PATH"; then
      echo "[ja-output-harness] codex_hooks = true already set in config.toml."
    else
      if [[ -n "$(tail -c1 "$CONFIG_PATH")" ]]; then
        printf '\n' >> "$CONFIG_PATH"
      fi
      printf 'codex_hooks = true\n' >> "$CONFIG_PATH"
      echo "[ja-output-harness] Set codex_hooks = true in config.toml."
    fi

    # Build absolute commands
    stop_cmd="bash \"$STOP_HOOK_PATH\""
    start_cmd="bash \"$START_HOOK_PATH\""
    # Resolve a Python 3 interpreter once so the JSON-escape helpers and the
    # template renderer use the same binary (gpt-5.4 review #47 — the previous
    # code hard-coded python3 and broke on Git Bash setups that only have `py`).
    HOOK_PY="$(resolve_python3)"

    # JSON-escape backslashes and double quotes
    stop_cmd_json="$(printf '%s' "$stop_cmd" | "$HOOK_PY" -c 'import json,sys;print(json.dumps(sys.stdin.read())[1:-1])' 2>/dev/null || printf '%s' "$stop_cmd" | sed 's/\\/\\\\/g; s/"/\\"/g')"
    start_cmd_json="$(printf '%s' "$start_cmd" | "$HOOK_PY" -c 'import json,sys;print(json.dumps(sys.stdin.read())[1:-1])' 2>/dev/null || printf '%s' "$start_cmd" | sed 's/\\/\\\\/g; s/"/\\"/g')"

    rendered="$("$HOOK_PY" - "$HOOKS_TEMPLATE" "$stop_cmd_json" "$start_cmd_json" <<'PY' 2>/dev/null || true
import sys, pathlib
path, stop_cmd, start_cmd = sys.argv[1], sys.argv[2], sys.argv[3]
tpl = pathlib.Path(path).read_text(encoding="utf-8")
sys.stdout.write(tpl.replace("{{STOP_COMMAND}}", stop_cmd).replace("{{SESSION_START_COMMAND}}", start_cmd))
PY
)"
    if [[ -z "$rendered" ]]; then
      echo "[ja-output-harness] Failed to render hooks.json template (python3 required)." >&2
    elif [[ -f "$HOOKS_JSON_PATH" ]]; then
      existing="$(cat "$HOOKS_JSON_PATH")"
      if [[ "$(printf '%s' "$existing" | tr -d '[:space:]')" == "$(printf '%s' "$rendered" | tr -d '[:space:]')" ]]; then
        echo "[ja-output-harness] hooks.json already up to date."
      elif [[ "$FORCE_HOOKS" == "true" ]]; then
        printf '%s' "$rendered" > "$HOOKS_JSON_PATH"
        echo "[ja-output-harness] Overwrote existing hooks.json (--force-hooks)."
      else
        echo "[ja-output-harness] Existing hooks.json at $HOOKS_JSON_PATH differs from bundled template." >&2
        echo "[ja-output-harness] Review and re-run with --force-hooks to overwrite, or merge manually." >&2
        echo "[ja-output-harness] Bundled template path: $HOOKS_TEMPLATE" >&2
      fi
    else
      printf '%s' "$rendered" > "$HOOKS_JSON_PATH"
      echo "[ja-output-harness] Wrote $HOOKS_JSON_PATH"
    fi
  fi
fi

echo ""
echo "[ja-output-harness] Installation complete."
echo "[ja-output-harness] Restart Codex (CLI or App) to activate the MCP server and the jp-harness-tune skill."
if [[ "$ENABLE_HOOKS" == "true" ]]; then
  echo "[ja-output-harness] Hooks (experimental) require Codex 0.120.0+ (CLI or App). See docs/HOOKS.md for details."
fi
