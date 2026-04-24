#!/usr/bin/env bash
# ja-output-harness: Stop hook (POSIX)
#
# Mode-aware: reads ~/.codex/state/jp-harness-mode. Supported modes:
#
#   strict      - v0.3.x behaviour: detect Japanese reply that skipped
#                 mcp__jp_lint__finalize and log a missing-finalize entry.
#   lite        - No MCP server installed. Run ja_output_harness.rules_cli
#                 on the assistant message and append violations to
#                 jp-harness-lite.jsonl. Zero output-token overhead.
#   strict-lite - Same lite lint, but emit {"decision":"block"} on ERROR
#                 violations so Codex self-corrects.
#
# Codex 0.120.x Stop hook stdin fields:
#   session_id, turn_id, transcript_path (nullable), cwd, hook_event_name,
#   model, permission_mode, stop_hook_active, last_assistant_message (nullable)
#
# Contract:
#   output : stdout = JSON hook response (empty for strict mode)
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

# Resolve repo root / venv python from this script's own absolute path so
# lite mode can invoke the installed package.
hook_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(dirname "$hook_dir")"
venv_py="$repo_root/.venv/bin/python"
if [ ! -x "$venv_py" ]; then
  venv_py="$repo_root/.venv/Scripts/python.exe"
fi

# Force UTF-8 and silence Python 3.12 DeprecationWarning for utcnow().
export PYTHONIOENCODING="utf-8"
export PYTHONWARNINGS="ignore::DeprecationWarning"
export JA_HARNESS_VENV_PY="$venv_py"
export JA_HARNESS_REPO_ROOT="$repo_root"

"$python_exec" -c '
import json, os, re, sys, subprocess, datetime, pathlib, tempfile

SCHEMA_VERSION = "1"
JP_RE = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")


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

    codex_home = os.environ.get("CODEX_HOME") or str(pathlib.Path.home() / ".codex")
    state_dir = pathlib.Path(codex_home) / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    mode_file = state_dir / "jp-harness-mode"
    mode = "strict"
    if mode_file.exists():
        try:
            mode = (mode_file.read_text(encoding="utf-8").strip() or "strict")
        except Exception:
            mode = "strict"

    # off: user toggled the harness off (e.g. ja-output-toggle off) so that
    # Codex output passes through untouched. Useful for A/B comparing
    # harness-on vs harness-off periods with ja-output-stats ab-report.
    if mode == "off":
        return 0

    if mode in ("lite", "strict-lite"):
        return _run_lite(payload, last_msg, state_dir, mode)

    # strict (original v0.3.x behaviour)
    return _run_strict(payload, last_msg, state_dir)


def _run_lite(payload, last_msg, state_dir, mode):
    venv_py = os.environ.get("JA_HARNESS_VENV_PY", "")
    if not venv_py or not os.path.exists(venv_py):
        return 0

    lite_state = state_dir / "jp-harness-lite.jsonl"
    session_id = str(payload.get("session_id", ""))

    tf = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", delete=False, suffix=".txt"
    )
    tempfile_path = tf.name
    try:
        tf.write(last_msg)
        tf.close()
        try:
            # Inner timeout deliberately tighter than the hook-wide 15s
            # declared in config/hooks.example.json, leaving ~5s headroom
            # for cold Python start on Windows (gpt-5.4 review MEDIUM #5).
            # --append-lite hands the jsonl write to metrics.record_lite,
            # which holds the rotate+lock primitives so concurrent Stop
            # hooks cannot interleave entries (Windows append is not
            # atomic). v0.4.2 follow-up to gpt-5.4 review #51.
            # `--session=` / `--mode=` use the equals form so a session id
            # that ever begins with `-` is not parsed as a separate flag
            # (gpt-5.4 review v0.4.2 MINOR).
            proc = subprocess.run(
                [
                    venv_py, "-m", "ja_output_harness.rules_cli",
                    "--check", tempfile_path,
                    "--append-lite", str(lite_state),
                    "--session=" + session_id,
                    "--mode=" + mode,
                ],
                capture_output=True, text=True, encoding="utf-8", timeout=10,
            )
        except Exception:
            return 0
        out = (proc.stdout or "").strip()
        if not out:
            return 0
        try:
            result = json.loads(out)
        except Exception:
            return 0
        rule_counts = result.get("rule_counts") or {}
        ok = bool(result.get("ok"))

        # Codex sets stop_hook_active = true when the current Stop event is
        # itself the result of a prior Stop hook continuation. Emitting
        # another block in that case can infinite-loop when the model
        # cannot clean the violation in one try. Log only; do not block.
        # (gpt-5.4 review BLOCKER #2)
        stop_hook_active = bool(payload.get("stop_hook_active"))
        if mode == "strict-lite" and not ok and not stop_hook_active:
            parts = [f"{r}: {n}" for r, n in rule_counts.items()]
            reason = (
                "ja-output-harness lite: " + ", ".join(parts)
                + ". 違反箇所を修正してから再送してください。"
            )
            sys.stdout.write(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    finally:
        try:
            os.unlink(tempfile_path)
        except Exception:
            pass
    return 0


def _run_strict(payload, last_msg, state_dir):
    transcript_path = payload.get("transcript_path") or ""
    if not transcript_path or not os.path.exists(transcript_path):
        return 0
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception:
        return 0
    # Require the jp_lint-scoped tool name. A bare '"name":"finalize"'
    # would also match tools on other MCP servers that happen to expose
    # something literally called "finalize" (gpt-5.4 follow-up review
    # MINOR).
    if "mcp__jp_lint__finalize" in content:
        return 0

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
