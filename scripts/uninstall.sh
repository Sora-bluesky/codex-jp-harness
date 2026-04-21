#!/usr/bin/env bash
# ja-output-harness uninstaller (macOS / Linux / Git Bash on Windows)
#
# Removes the ja-output-harness footprint from ~/.codex/:
#   * [mcp_servers.jp_lint] block in config.toml
#   * codex_hooks = true toggle in config.toml (only if installed by us)
#   * Stop / SessionStart entries in hooks.json that point at
#     ja-output-harness hook scripts
# AGENTS.md edits remain manual — we print a removal notice — because the
# rule block may coexist with other user-authored rules.

set -euo pipefail

CODEX_DIR="$HOME/.codex"
CONFIG_PATH="$CODEX_DIR/config.toml"
HOOKS_JSON_PATH="$CODEX_DIR/hooks.json"

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "[ja-output-harness] Codex config.toml not found at $CONFIG_PATH" >&2
  exit 1
fi

# Resolve a Python interpreter to run the hooks.json cleanup helper.
# Falls back to `sed` only when no Python 3.8+ is available.
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

# 2. Remove codex_hooks = true (only touches the line the installer added).
if grep -qE '^[[:space:]]*codex_hooks[[:space:]]*=[[:space:]]*true\b' "$CONFIG_PATH"; then
  tmp="$(mktemp)"
  grep -vE '^[[:space:]]*codex_hooks[[:space:]]*=[[:space:]]*true\b' "$CONFIG_PATH" > "$tmp" || true
  mv "$tmp" "$CONFIG_PATH"
  echo "[ja-output-harness] Removed codex_hooks = true from config.toml"
fi

# 3. hooks.json: remove any entry whose command references ja-output-harness.
if [[ -f "$HOOKS_JSON_PATH" ]]; then
  if [[ -z "$UNINSTALL_PY" ]]; then
    echo "[ja-output-harness] hooks.json cleanup requires Python 3.8+; skipping. Remove jp-harness entries manually: $HOOKS_JSON_PATH" >&2
  else
    "$UNINSTALL_PY" - "$HOOKS_JSON_PATH" <<'PY'
import json, sys, pathlib
path = pathlib.Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception as exc:
    print(f"[ja-output-harness] Skipping hooks.json (cannot parse): {exc}", file=sys.stderr)
    sys.exit(0)

hooks = data.get("hooks") if isinstance(data, dict) else None
if not isinstance(hooks, dict):
    print("[ja-output-harness] hooks.json has no top-level hooks object; nothing to clean.")
    sys.exit(0)

MARKER = "ja-output-harness"
LEGACY = "codex-jp-harness"  # pre-v0.3.0 install footprint, clean that too.


def is_ours(entry):
    if not isinstance(entry, dict):
        return False
    inner = entry.get("hooks")
    if isinstance(inner, list):
        for item in inner:
            cmd = (item or {}).get("command", "") if isinstance(item, dict) else ""
            if MARKER in cmd or LEGACY in cmd:
                return True
    cmd = entry.get("command", "")
    return MARKER in cmd or LEGACY in cmd


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
    else:
        # Nothing useful left — remove the file so Codex does not load an empty schema.
        path.unlink()
        print(f"[ja-output-harness] Removed empty hooks.json (backup at {backup})")
else:
    print("[ja-output-harness] No ja-output-harness hook entries found in hooks.json.")
PY
  fi
else
  echo "[ja-output-harness] hooks.json not present; nothing to clean."
fi

echo ""
echo "[ja-output-harness] Manual step (still required):"
echo "[ja-output-harness]   Edit ~/.codex/AGENTS.md and remove the quality-gate rule block."
echo "[ja-output-harness]   The uninstaller does not touch AGENTS.md because user-authored rules may be interleaved."
echo "[ja-output-harness] Then restart Codex (CLI or App)."
