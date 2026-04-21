#!/usr/bin/env bash
# ja-output-harness: Stop hook (POSIX)
#
# Detects whether the just-completed turn produced a Japanese assistant reply
# without calling mcp__jp_lint__finalize. Records a missing-finalize entry to
# ~/.codex/state/jp-harness.jsonl.
#
# Codex 0.120.x Stop hook stdin fields:
#   session_id, turn_id, transcript_path (nullable), cwd, hook_event_name,
#   model, permission_mode, stop_hook_active, last_assistant_message (nullable)
#
# Contract:
#   output : stdout empty
#   exit   : 0 always (never break the session)

set +e

python_exec=""
for c in python3 python py; do
  if command -v "$c" >/dev/null 2>&1; then
    # Reject Microsoft Store stub on Windows which prints "Python" and exits non-zero.
    if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1; then
      python_exec="$c"
      break
    fi
  fi
done
if [ -z "$python_exec" ]; then
  exit 0
fi

# Force UTF-8 and silence Python 3.12 DeprecationWarning for utcnow().
export PYTHONIOENCODING="utf-8"
export PYTHONWARNINGS="ignore::DeprecationWarning"

"$python_exec" -c '
import json, os, re, sys, datetime, pathlib

SCHEMA_VERSION = "1"
JP_RE = re.compile(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]")

def main():
    try:
        raw = sys.stdin.read()
    except Exception:
        return 0
    if not raw or not raw.strip():
        return 0
    try:
        payload = json.loads(raw)
    except Exception:
        return 0
    last_msg = payload.get("last_assistant_message") or ""
    if not last_msg or not JP_RE.search(str(last_msg)):
        return 0
    transcript_path = payload.get("transcript_path") or ""
    if not transcript_path or not os.path.exists(transcript_path):
        return 0
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception:
        return 0
    # Match the MCP tool call exactly, not the bare word. The prior
    # substring check misfired whenever the user or assistant merely
    # mentioned the word "finalize" in prose or a quoted reply
    # (gpt-5.4 review #54).
    if re.search(r"mcp__jp_lint__finalize|\"name\"\s*:\s*\"finalize\"", content):
        return 0
    codex_home = os.environ.get("CODEX_HOME") or str(pathlib.Path.home() / ".codex")
    state_dir = pathlib.Path(codex_home) / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "jp-harness.jsonl"
    now = datetime.datetime.utcnow()
    expires = now + datetime.timedelta(hours=24)
    entry = {
        "schema_version": SCHEMA_VERSION,
        "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "session": str(payload.get("session_id", "")),
        "violation": "missing-finalize",
        "expires": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        with state_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        sys.stderr.write("[ja-output-harness] stop-finalize-check write error: " + str(e) + "\n")
    return 0

try:
    sys.exit(main())
except Exception as e:
    sys.stderr.write("[ja-output-harness] stop-finalize-check error: " + str(e) + "\n")
    sys.exit(0)
'
exit 0
