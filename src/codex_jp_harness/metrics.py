"""Metrics recording for `finalize` calls.

Each call appends one JSON Lines entry to
``$CODEX_HOME/state/jp-harness-metrics.jsonl`` (default
``~/.codex/state/jp-harness-metrics.jsonl``). The server uses these to
let ``codex-jp-stats`` compute draft size distribution, violations
distribution, elapsed time distribution, and a same-turn retry estimate.

Write failures are silent: a failing log must never break the tool call
that the user depends on.
"""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1"


def _codex_home() -> Path:
    home = os.environ.get("CODEX_HOME")
    if home:
        return Path(home)
    return Path.home() / ".codex"


def metrics_path() -> Path:
    """Return the path to the metrics jsonl file."""
    return _codex_home() / "state" / "jp-harness-metrics.jsonl"


def record(
    *,
    draft: str,
    violations_count: int,
    severity_counts: dict[str, int],
    response: dict[str, Any],
    elapsed_ms: float,
    path: Path | None = None,
) -> None:
    """Append one metric line. Swallows all I/O errors."""
    try:
        target = path if path is not None else metrics_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        draft_bytes = len(draft.encode("utf-8"))
        response_bytes = len(json.dumps(response, ensure_ascii=False).encode("utf-8"))
        entry = {
            "schema_version": SCHEMA_VERSION,
            "ts": datetime.datetime.now(datetime.timezone.utc)
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
            "response_bytes": response_bytes,
            "elapsed_ms": round(elapsed_ms, 2),
            "ok": bool(response.get("ok", False)),
        }
        with target.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        # Never let a metrics write failure break the tool call.
        return
