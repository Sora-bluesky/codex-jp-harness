"""Metrics recording for `finalize` calls.

Each call appends one JSON Lines entry to
``$CODEX_HOME/state/jp-harness-metrics.jsonl`` (default
``~/.codex/state/jp-harness-metrics.jsonl``). The server uses these to
let ``ja-output-stats`` compute draft size distribution, violations
distribution, elapsed time distribution, and a same-turn retry estimate.

Write failures are silent: a failing log must never break the tool call
that the user depends on.
"""

from __future__ import annotations

import datetime
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "2"

# Rotate to <name>.1.jsonl once the active file exceeds this many bytes.
# 20 MB holds ~80k entries at ~250 B each — long enough for monthly
# aggregates and short enough to keep `ja-output-stats show` fast.
DEFAULT_MAX_BYTES = 20 * 1024 * 1024


def _codex_home() -> Path:
    home = os.environ.get("CODEX_HOME")
    if home:
        return Path(home)
    return Path.home() / ".codex"


def metrics_path() -> Path:
    """Return the path to the metrics jsonl file."""
    return _codex_home() / "state" / "jp-harness-metrics.jsonl"


def lite_metrics_path() -> Path:
    """Return the path to the lite-mode Stop hook jsonl file.

    Written via :func:`record_lite` (called by ``rules_cli`` from
    ``hooks/stop-finalize-check.{ps1,sh}``). Shares the rotate+lock
    primitives with :func:`record` so concurrent Stop hook invocations
    on Windows (where O_APPEND is not atomic) cannot interleave
    entries; if the lock cannot be acquired the metric is dropped
    rather than written without protection (see :func:`record_lite`).
    """
    return _codex_home() / "state" / "jp-harness-lite.jsonl"


def archive_path(active: Path) -> Path:
    """Return the 1-generation archive path for the given active file."""
    return active.with_name(active.stem + ".1" + active.suffix)


def _maybe_rotate(target: Path, max_bytes: int) -> None:
    """Rotate target to <name>.1.jsonl if it exceeds max_bytes. O(1)."""
    try:
        if target.exists() and target.stat().st_size >= max_bytes:
            archive = archive_path(target)
            if archive.exists():
                archive.unlink()
            target.rename(archive)
    except Exception:
        return


_ROTATE_LOCK_TIMEOUT = 1.0  # seconds — metrics is best-effort; never block the tool.


@contextmanager
def _rotate_lock(target: Path, timeout: float = _ROTATE_LOCK_TIMEOUT):
    """Best-effort cross-platform lock around rotate+append.

    Without this, two concurrent ``finalize`` calls can race on
    ``_maybe_rotate`` and either duplicate the archive copy or lose the
    incoming record. The lock is advisory (``O_CREAT|O_EXCL`` sentinel file)
    and its timeout is short: metrics are diagnostic data, so if we cannot
    acquire the lock we silently skip rather than delay the user's
    ``finalize`` call (gpt-5.4 review #51).
    """
    lock_path = target.with_suffix(target.suffix + ".lock")
    deadline = time.monotonic() + timeout
    acquired = False
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            acquired = True
            break
        except (FileExistsError, PermissionError):
            if time.monotonic() > deadline:
                # Stale lock (crashed writer)? Reclaim if older than timeout.
                try:
                    if lock_path.exists():
                        age = time.time() - lock_path.stat().st_mtime
                        if age > timeout:
                            lock_path.unlink()
                            continue
                except OSError:
                    pass
                break  # give up silently; metrics are advisory
            time.sleep(0.005)
    try:
        yield acquired
    finally:
        if acquired:
            try:
                lock_path.unlink()
            except OSError:
                pass


def record(
    *,
    draft: str,
    violations_count: int,
    severity_counts: dict[str, int],
    response: dict[str, Any],
    elapsed_ms: float,
    path: Path | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    fixed: bool = False,
    rule_counts: dict[str, int] | None = None,
) -> None:
    """Append one metric line. Swallows all I/O errors.

    The active file is rotated to ``<name>.1.jsonl`` when it first reaches
    ``max_bytes`` (default 20 MB). Only one archive generation is kept;
    prior archives are removed on rotation so total disk usage is bounded
    at roughly ``2 * max_bytes``.

    ``fixed`` is ``True`` when the server used the fast-path auto-rewrite
    instead of handing violations back to the caller.

    ``rule_counts`` is a rule-name → count map (e.g. ``{"bare_identifier": 3}``)
    added in schema v2 to diagnose fast-path misses: when a draft fails with
    ERRORs but no fast-path fires, ``rule_counts`` reveals which rule made the
    violation set non-auto-fixable. Missing on schema v1 entries; readers
    must default to ``{}``.
    """
    try:
        target = path if path is not None else metrics_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        draft_bytes = len(draft.encode("utf-8"))
        response_bytes = len(json.dumps(response, ensure_ascii=False).encode("utf-8"))
        entry = {
            "schema_version": SCHEMA_VERSION,
            "ts": datetime.datetime.now(datetime.UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "draft_chars": len(draft),
            "draft_bytes": draft_bytes,
            "violations_count": violations_count,
            "severity_counts": {
                "ERROR": int(severity_counts.get("ERROR", 0)),
                "WARNING": int(severity_counts.get("WARNING", 0)),
                "INFO": int(severity_counts.get("INFO", 0)),
            },
            "rule_counts": {str(k): int(v) for k, v in (rule_counts or {}).items()},
            "response_bytes": response_bytes,
            "elapsed_ms": round(elapsed_ms, 2),
            "ok": bool(response.get("ok", False)),
            "fixed": bool(fixed),
        }
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with _rotate_lock(target):
            # Both rotate and append happen inside the critical section so
            # no other writer can slip in between the archive rename and the
            # fresh-file append. If the lock was not acquired we still write
            # best-effort — better to risk a rare duplicate on the rotate
            # boundary than to drop the record entirely.
            _maybe_rotate(target, max_bytes)
            with target.open("a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        # Never let a metrics write failure break the tool call.
        return


# Schema version of jp-harness-lite.jsonl entries. Kept distinct from the
# strict metrics SCHEMA_VERSION so the two files can evolve independently.
LITE_SCHEMA_VERSION = "1"


def record_lite(
    *,
    session: str,
    mode: str,
    ok: bool,
    violation_count: int,
    rule_counts: dict[str, int] | None = None,
    path: Path | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    expires_hours: int = 24,
) -> None:
    """Append one lite-mode Stop hook entry under the rotate+lock primitives.

    The schema mirrors what ``hooks/stop-finalize-check.{ps1,sh}`` wrote
    pre-v0.4.2 directly via ``Add-Content`` / raw ``open('a')`` — those
    paths are not atomic on Windows. Routing the write through Python
    lets the hook share :func:`_rotate_lock` with :func:`record`, so
    concurrent Stop events cannot interleave half-written lines.

    Like :func:`record`, every I/O failure is swallowed: a metrics drop
    must never break the user's Codex turn (gpt-5.4 review #51).

    Unlike :func:`record`, when the rotate lock cannot be acquired we
    drop the entry rather than fall back to an unprotected append.
    Preventing the Windows non-atomic append is the entire reason this
    function exists, so a "best-effort" fallback would defeat the
    purpose (gpt-5.4 review v0.4.2 MEDIUM #2).
    """
    try:
        target = path if path is not None else lite_metrics_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.datetime.now(datetime.UTC).replace(microsecond=0)
        expires = now + datetime.timedelta(hours=expires_hours)
        entry = {
            "schema_version": LITE_SCHEMA_VERSION,
            "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "session": str(session),
            "ok": bool(ok),
            "violation_count": int(violation_count),
            "rule_counts": {str(k): int(v) for k, v in (rule_counts or {}).items()},
            "mode": str(mode),
            "expires": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with _rotate_lock(target) as acquired:
            if not acquired:
                return
            _maybe_rotate(target, max_bytes)
            with target.open("a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        return
