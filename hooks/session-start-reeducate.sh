#!/usr/bin/env bash
# ja-output-harness: SessionStart hook (POSIX)
#
# Reads new entries from both harness jsonl files and emits a short
# reeducation prompt (hard cap 400 chars).
#
#   ~/.codex/state/jp-harness.jsonl       strict-mode missing-finalize logs
#   ~/.codex/state/jp-harness-lite.jsonl  lite / strict-lite ok=false logs
#
# Consumption is tracked by byte offset in
# ~/.codex/state/jp-harness-cursor.json, written via os.replace for
# atomic rename, so concurrent Stop-hook appends cannot be overwritten
# and unprocessed rows cannot be silently dropped (gpt-5.4 v0.4.0 review
# MAJOR #2/#3).
#
# Triggers on "startup" and "clear"; "resume" is suppressed.
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

export PYTHONIOENCODING="utf-8"
export PYTHONWARNINGS="ignore::DeprecationWarning"

"$python_exec" -c '
import json, os, sys, datetime, pathlib
from collections import Counter

MAX_CHARS = 400


def read_new_entries(path, offset):
    """Return (entries, new_offset). Entries are parsed JSON rows from
    ``path`` starting at ``offset`` bytes through current EOF.

    If the file has been truncated below ``offset`` we reset to 0 — that
    only happens on an unexpected rotation, which is the rarer event.
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        return [], offset
    if size < offset:
        offset = 0
    if size == offset:
        return [], offset
    try:
        with open(path, "rb") as f:
            f.seek(offset)
            data = f.read()
    except OSError:
        return [], offset
    text = data.decode("utf-8", errors="replace")
    entries = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except Exception:
            continue
    return entries, size


def save_cursor(path, data):
    """Atomic write via temp + os.replace (cross-platform atomic rename)."""
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _parse_expires(value):
    if not value:
        return None
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


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
    state_dir = pathlib.Path(codex_home) / "state"
    if not state_dir.exists():
        return 0

    # off: user toggled the harness off (ja-output-toggle off).
    # Skip reeducation so the session starts clean for A/B comparison.
    mode_file = state_dir / "jp-harness-mode"
    if mode_file.exists():
        try:
            _mode = mode_file.read_text(encoding="utf-8").strip()
        except Exception:
            _mode = ""
        if _mode == "off":
            return 0

    strict_file = state_dir / "jp-harness.jsonl"
    lite_file   = state_dir / "jp-harness-lite.jsonl"
    cursor_file = state_dir / "jp-harness-cursor.json"

    if cursor_file.exists():
        try:
            cursor = json.loads(cursor_file.read_text(encoding="utf-8"))
        except Exception:
            cursor = {}
    else:
        # First run: skip any pre-install history so a stale backlog does
        # not get dumped into the first prompt.
        cursor = {
            "strict_byte_offset": strict_file.stat().st_size if strict_file.exists() else 0,
            "lite_byte_offset":   lite_file.stat().st_size   if lite_file.exists()   else 0,
        }
        save_cursor(str(cursor_file), cursor)
        return 0

    strict_offset = int(cursor.get("strict_byte_offset") or 0)
    lite_offset   = int(cursor.get("lite_byte_offset")   or 0)

    strict_entries, new_strict_offset = read_new_entries(str(strict_file), strict_offset)
    lite_entries,   new_lite_offset   = read_new_entries(str(lite_file),   lite_offset)

    now = datetime.datetime.utcnow()

    strict_violations = []
    for e in strict_entries:
        if not e.get("violation"):
            continue
        exp = _parse_expires(e.get("expires"))
        if exp is None or exp <= now:
            continue
        strict_violations.append(e)

    lite_violations = []
    for e in lite_entries:
        if e.get("ok") is not False:
            continue
        exp = _parse_expires(e.get("expires"))
        if exp is not None and exp <= now:
            continue
        lite_violations.append(e)

    # Always advance the cursor, even when parts is empty — we still
    # consumed the bytes (they contained nothing actionable).
    cursor["strict_byte_offset"] = new_strict_offset
    cursor["lite_byte_offset"]   = new_lite_offset
    save_cursor(str(cursor_file), cursor)

    parts = []
    if strict_violations:
        counts = Counter(v.get("violation", "unknown") for v in strict_violations)
        detail = "、".join(f"{name} ({n}回)" for name, n in counts.most_common(3))
        parts.append(
            f"前回セッションで mcp__jp_lint__finalize の呼び忘れ {len(strict_violations)} 件（{detail}）。"
            "日本語応答の前に必ず finalize を呼ぶこと。"
            "除外は 4 パターンのみ（コード単独 / 20字以内相槌 / yes-no / 日本語なし）。"
        )
    if lite_violations:
        rule_agg = Counter()
        for v in lite_violations:
            rc = v.get("rule_counts") or {}
            if not isinstance(rc, dict):
                continue
            for rule, n in rc.items():
                try:
                    rule_agg[str(rule)] += int(n)
                except (TypeError, ValueError):
                    continue
        if rule_agg:
            detail = "、".join(f"{name} ({n}回)" for name, n in rule_agg.most_common(3))
            parts.append(
                f"前回セッションで日本語品質違反 {len(lite_violations)} 件（{detail}）。"
                "違反ルールを避けて応答すること。"
            )
        else:
            parts.append(f"前回セッションで日本語品質違反 {len(lite_violations)} 件。")

    if not parts:
        return 0

    msg = "[ja-output-harness] " + " ".join(parts)
    if len(msg) > MAX_CHARS:
        msg = msg[:MAX_CHARS]
    sys.stdout.write(msg + "\n")
    return 0


try:
    sys.exit(main())
except Exception as e:
    sys.stderr.write("[ja-output-harness] session-start-reeducate error: " + str(e) + "\n")
    sys.exit(0)
'
exit 0
