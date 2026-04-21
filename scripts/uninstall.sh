#!/usr/bin/env bash
# ja-output-harness uninstaller (macOS / Linux / Git Bash on Windows)
#
# Removes the ja-output-harness footprint from ~/.codex/:
#   * [mcp_servers.jp_lint] block in config.toml
#   * Stop / SessionStart entries in hooks.json whose command references
#     this repo's hook scripts (absolute path match, plus marker fallback)
#   * codex_hooks = true toggle — only when the file no longer lists any
#     hooks at all after pruning ours (never breaks a coexisting hook setup)
# AGENTS.md edits remain manual because the rule block often interleaves
# with user-authored rules.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

CODEX_DIR="$HOME/.codex"
CONFIG_PATH="$CODEX_DIR/config.toml"
HOOKS_JSON_PATH="$CODEX_DIR/hooks.json"

# Hook script absolute paths as the installer would have written them.
# Used for exact-ownership matching before falling back to the repo marker.
STOP_HOOK_ABS="$REPO_ROOT/hooks/stop-finalize-check.sh"
START_HOOK_ABS="$REPO_ROOT/hooks/session-start-reeducate.sh"

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "[ja-output-harness] Codex config.toml not found at $CONFIG_PATH" >&2
  exit 1
fi

# Resolve a Python interpreter to run the hooks.json cleanup helper.
resolve_python3() {
  for cand in python3 python py; do
    if command -v "$cand" >/dev/null 2>&1; then
      if "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1; then
        printf '%s' "$cand"
        return 0
      fi
    fi
  done
  printf ''
}

UNINSTALL_PY="$(resolve_python3)"

# 1. Remove [mcp_servers.jp_lint] block.
if ! grep -q '^\[mcp_servers\.jp_lint\]' "$CONFIG_PATH"; then
  echo "[ja-output-harness] [mcp_servers.jp_lint] not found; skipping."
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
  echo "[ja-output-harness] Removed [mcp_servers.jp_lint] from config.toml"
  echo "[ja-output-harness] Backup saved to $backup"
fi

# 2. hooks.json: remove entries whose command invokes ja-output-harness hook
#    scripts. Match on absolute path first, then fall back to the repo name
#    marker so legacy installs (or rename-after-install) are still cleaned.
#    HOOKS_EMPTY sidecar tells step 3 whether hooks.json still has anything.
HOOKS_EMPTY="no"
if [[ -f "$HOOKS_JSON_PATH" ]]; then
  if [[ -z "$UNINSTALL_PY" ]]; then
    echo "[ja-output-harness] hooks.json cleanup requires Python 3.8+; skipping. Remove jp-harness entries manually: $HOOKS_JSON_PATH" >&2
  else
    result_file="$(mktemp)"
    "$UNINSTALL_PY" - "$HOOKS_JSON_PATH" "$STOP_HOOK_ABS" "$START_HOOK_ABS" "$result_file" <<'PY' || true
import json, sys, pathlib

path = pathlib.Path(sys.argv[1])
stop_abs = sys.argv[2]
start_abs = sys.argv[3]
result = pathlib.Path(sys.argv[4])

try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception as exc:
    result.write_text("parse_error", encoding="utf-8")
    print(f"[ja-output-harness] Skipping hooks.json (cannot parse): {exc}", file=sys.stderr)
    sys.exit(0)

hooks = data.get("hooks") if isinstance(data, dict) else None
if not isinstance(hooks, dict):
    result.write_text("no_hooks_section", encoding="utf-8")
    print("[ja-output-harness] hooks.json has no top-level hooks object; nothing to clean.")
    sys.exit(0)

MARKERS = ("ja-output-harness", "codex-jp-harness")
OWNED_PATHS = {p for p in (stop_abs, start_abs) if p}


def is_ours(entry):
    if not isinstance(entry, dict):
        return False
    inner = entry.get("hooks")
    cmds = []
    if isinstance(inner, list):
        for item in inner:
            if isinstance(item, dict):
                cmds.append(str(item.get("command", "")))
    cmds.append(str(entry.get("command", "")))
    for cmd in cmds:
        if not cmd:
            continue
        if any(owned and owned in cmd for owned in OWNED_PATHS):
            return True
        if any(marker in cmd for marker in MARKERS):
            return True
    return False


removed = 0
for event, entries in list(hooks.items()):
    if not isinstance(entries, list):
        continue
    kept = [e for e in entries if not is_ours(e)]
    removed += len(entries) - len(kept)
    if kept:
        hooks[event] = kept
    else:
        del hooks[event]

if not hooks:
    data.pop("hooks", None)

if removed:
    backup = path.with_suffix(path.suffix + ".bak")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    if data:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"[ja-output-harness] Pruned {removed} hook entrie(s) from {path}")
        result.write_text("pruned_non_empty", encoding="utf-8")
    else:
        path.unlink()
        print(f"[ja-output-harness] Removed empty hooks.json (backup at {backup})")
        result.write_text("pruned_empty", encoding="utf-8")
else:
    if not hooks:
        result.write_text("already_empty", encoding="utf-8")
    else:
        result.write_text("no_match_non_empty", encoding="utf-8")
    print("[ja-output-harness] No ja-output-harness hook entries found in hooks.json.")
PY
    HOOKS_STATUS="$(cat "$result_file" 2>/dev/null || echo "")"
    rm -f "$result_file"
    case "$HOOKS_STATUS" in
      pruned_empty|already_empty|no_hooks_section) HOOKS_EMPTY="yes" ;;
      *) HOOKS_EMPTY="no" ;;
    esac
  fi
else
  HOOKS_EMPTY="yes"
  echo "[ja-output-harness] hooks.json not present; nothing to clean."
fi

# 3. Remove codex_hooks = true only when there are no hooks left overall.
#    Otherwise we would silently disable every coexisting hook.
if grep -qE '^[[:space:]]*codex_hooks[[:space:]]*=[[:space:]]*true\b' "$CONFIG_PATH"; then
  if [[ "$HOOKS_EMPTY" == "yes" ]]; then
    tmp="$(mktemp)"
    grep -vE '^[[:space:]]*codex_hooks[[:space:]]*=[[:space:]]*true\b' "$CONFIG_PATH" > "$tmp" || true
    mv "$tmp" "$CONFIG_PATH"
    echo "[ja-output-harness] Removed codex_hooks = true from config.toml (no remaining hooks)."
  else
    echo "[ja-output-harness] Left codex_hooks = true in place — other hooks are still registered in hooks.json."
  fi
fi

# 4. Remove the mode marker so a future install default re-enters the
#    "new user" path.
MODE_MARKER="$CODEX_DIR/state/jp-harness-mode"
if [[ -f "$MODE_MARKER" ]]; then
  rm -f "$MODE_MARKER"
  echo "[ja-output-harness] Removed mode marker: $MODE_MARKER"
fi

echo ""
echo "[ja-output-harness] Manual step (still required):"
echo "[ja-output-harness]   Edit ~/.codex/AGENTS.md and remove the quality-gate rule block."
echo "[ja-output-harness]   The uninstaller does not touch AGENTS.md because user-authored rules may be interleaved."
echo "[ja-output-harness] Then restart Codex (CLI or App)."
