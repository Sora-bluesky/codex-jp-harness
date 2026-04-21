#!/usr/bin/env bash
# ja-output-harness: SessionStart hook (POSIX)
#
# Reads ~/.codex/state/jp-harness.jsonl and emits a reeducation prompt when
# source is "startup" or "clear". Suppresses on "resume".
#
# Contract:
#   input  : stdin JSON  { session_id?, source?: "startup"|"resume"|"clear" }
#   output : stdout reeducation prompt (or empty)
#   exit   : 0 always

set +e

python_exec=""
for c in python3 python py; do
  if command -v "$c" >/dev/null 2>&1; then
    if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1; then
      python_exec="$c"
      break
    fi
  fi
done
if [ -z "$python_exec" ]; then
  exit 0
fi

# Force UTF-8 stdout on Windows (default cp932 would mojibake Japanese text).
export PYTHONIOENCODING="utf-8"
export PYTHONWARNINGS="ignore::DeprecationWarning"

"$python_exec" -c '
import json, os, sys, datetime, pathlib
from collections import Counter

MAX_CHARS = 400

def main():
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    source = "startup"
    if raw and raw.strip():
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict) and payload.get("source"):
                source = str(payload["source"])
        except Exception:
            pass
    if source == "resume":
        return 0
    codex_home = os.environ.get("CODEX_HOME") or str(pathlib.Path.home() / ".codex")
    state_file = pathlib.Path(codex_home) / "state" / "jp-harness.jsonl"
    if not state_file.exists():
        return 0
    try:
        lines = state_file.read_text(encoding="utf-8").splitlines()
    except Exception:
        return 0
    tail = lines[-20:]
    now = datetime.datetime.utcnow()
    active = []
    keep = []
    for line in tail:
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            exp = datetime.datetime.strptime(entry["expires"], "%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            continue
        if exp <= now:
            continue
        if entry.get("consumed"):
            keep.append(line)
            continue
        active.append(entry)
    if not active:
        return 0
    counts = Counter(a.get("violation", "unknown") for a in active)
    top = counts.most_common(3)
    detail = "、".join(f"{name} ({n}回)" for name, n in top)
    msg = (
        "[ja-output-harness] 前回セッションで mcp__jp_lint__finalize の呼び忘れを検出しました。"
        f"内訳: {detail}。"
        "日本語応答を返す前に必ず finalize を呼んでください。"
        "除外は 4 パターンのみ（コード単独 / 20字以内相槌 / yes-no / 日本語なし）。迷ったら呼ぶ。"
    )
    if len(msg) > MAX_CHARS:
        msg = msg[:MAX_CHARS]
    sys.stdout.write(msg + "\n")
    for a in active:
        a["consumed"] = True
        keep.append(json.dumps(a, ensure_ascii=False))
    try:
        state_file.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
    except Exception as e:
        sys.stderr.write("[ja-output-harness] session-start-reeducate write error: " + str(e) + "\n")
    return 0

try:
    sys.exit(main())
except Exception as e:
    sys.stderr.write("[ja-output-harness] session-start-reeducate error: " + str(e) + "\n")
    sys.exit(0)
'
exit 0
