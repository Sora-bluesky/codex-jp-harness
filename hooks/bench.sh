#!/usr/bin/env bash
# ja-output-harness: hooks benchmark (POSIX)
#
# Runs each hook 10 times with synthetic payload and reports mean / max latency.
# Targets:
#   Stop hook        : < 50 ms (mean)
#   SessionStart hook: < 100 ms (mean)
#
# Usage:
#   bash hooks/bench.sh

set -euo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STOP_HOOK="$HOOK_DIR/stop-finalize-check.sh"
START_HOOK="$HOOK_DIR/session-start-reeducate.sh"

python_exec=""
for c in python3 python py; do
  if command -v "$c" >/dev/null 2>&1; then python_exec="$c"; break; fi
done
if [ -z "$python_exec" ]; then
  echo "bench requires python3 (for timing calculation)" >&2
  exit 1
fi

STOP_PAYLOAD='{"session_id":"bench-session","turn_id":"bench-turn","transcript_path":null,"last_assistant_message":"これは日本語の応答です。finalize を呼ばずに終わったケースの検査。","stop_hook_active":false,"hook_event_name":"Stop"}'
START_PAYLOAD='{"session_id":"bench-session","source":"startup","hook_event_name":"SessionStart"}'

measure_hook() {
  local name="$1"
  local script="$2"
  local payload="$3"
  local target="$4"
  local durations=""
  for i in $(seq 1 10); do
    local start_ns end_ns elapsed_ms
    start_ns=$("$python_exec" -c 'import time; print(int(time.time()*1000))')
    printf '%s' "$payload" | bash "$script" >/dev/null 2>&1 || true
    end_ns=$("$python_exec" -c 'import time; print(int(time.time()*1000))')
    elapsed_ms=$((end_ns - start_ns))
    durations="$durations $elapsed_ms"
  done
  "$python_exec" -c '
import sys
vals = [int(x) for x in "'$durations'".split()]
mean = sum(vals)/len(vals)
mx = max(vals)
target = '$target'
name = "'$name'"
status = "PASS" if mean <= target else "WARN"
print(f"[{status}] {name}: mean={mean:.1f} ms, max={mx:.1f} ms (target <{target} ms)")
'
}

echo '[ja-output-harness] hooks benchmark (10 runs each)'
measure_hook 'Stop'         "$STOP_HOOK"  "$STOP_PAYLOAD"  50
measure_hook 'SessionStart' "$START_HOOK" "$START_PAYLOAD" 100
