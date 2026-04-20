"""MCP server exposing the `finalize` tool for Codex (CLI / App).

Codex calls `mcp__jp_lint__finalize(draft)` before delivering a Japanese
technical report. If violations are found, Codex is expected to rewrite
and call again until `ok: true` is returned.
"""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from codex_jp_harness import metrics
from codex_jp_harness.rules import (
    Violation,
    apply_auto_fix,
    extract_replacement,
    lint,
    load_rules,
    resolve_user_config_path,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RULES_PATH = REPO_ROOT / "config" / "banned_terms.yaml"

mcp = FastMCP("jp_lint")


def _summarize(violations: list[Violation]) -> str:
    """Build a human-readable summary string with severity counts."""
    counts = Counter(v.severity or "ERROR" for v in violations)
    parts = [f"{counts[s]} {s}" for s in ("ERROR", "WARNING", "INFO") if counts[s]]
    return f"{len(violations)}件の違反を検出 ({', '.join(parts)})"


@mcp.tool()
def finalize(draft: str) -> dict[str, Any]:
    """日本語技術報告のドラフトを検査する。

    違反があれば修正指示を返し、Codex は指示に従って書き直して再呼び出しする。
    severity は ERROR / WARNING / INFO の三段階。ERROR は必ず修正、WARNING は
    推奨修正、INFO は参考。

    Args:
        draft: 日本語技術報告のドラフト全文

    Returns:
        合格 (ERROR が 0 件): ``{"ok": True}``
        不合格: ``{"ok": False, "violations": [...], "summary": "..."}``
    """
    started = time.perf_counter()
    cfg = load_rules(RULES_PATH, resolve_user_config_path())
    violations = lint(draft, cfg)
    error_violations = [v for v in violations if (v.severity or "ERROR") == "ERROR"]
    severity_counts = Counter(v.severity or "ERROR" for v in violations)
    fixed = False

    if error_violations and _fast_path_applicable(error_violations):
        rewritten = apply_auto_fix(draft, error_violations)
        new_violations = lint(rewritten, cfg)
        new_errors = [v for v in new_violations if (v.severity or "ERROR") == "ERROR"]
        if not new_errors:
            # Auto-fix cleared all ERROR violations — skip the LLM rewrite loop.
            fix_parts = [
                f"{v.term} → {extract_replacement(v.suggest)}" for v in error_violations
            ]
            response: dict[str, Any] = {
                "ok": True,
                "fixed": True,
                "rewritten": rewritten,
                "summary": f"{len(error_violations)}件を自動修正 ({', '.join(fix_parts)})",
            }
            if new_violations:
                response["advisories"] = [v.to_dict() for v in new_violations]
            fixed = True
            violations = new_violations
            severity_counts = Counter(v.severity or "ERROR" for v in violations)
        else:
            # Auto-fix introduced new errors — fall through to the regular loop.
            response = _build_standard_response(violations, error_violations)
    elif not error_violations:
        if not violations:
            response = {"ok": True}
        else:
            response = {
                "ok": True,
                "advisories": [v.to_dict() for v in violations],
                "summary": _summarize(violations),
            }
    else:
        response = _build_standard_response(violations, error_violations)

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    metrics.record(
        draft=draft,
        violations_count=len(violations),
        severity_counts=dict(severity_counts),
        response=response,
        elapsed_ms=elapsed_ms,
        fixed=fixed,
    )
    return response


def _fast_path_applicable(error_violations: list[Violation]) -> bool:
    """The fast path runs when every ERROR is a banned_term that has a usable replacement."""
    if not error_violations:
        return False
    for v in error_violations:
        if v.rule != "banned_term":
            return False
        if not extract_replacement(v.suggest):
            return False
    return True


def _build_standard_response(
    violations: list[Violation], error_violations: list[Violation]
) -> dict[str, Any]:
    # Parameter kept for symmetry with callers; error subset derives from violations.
    del error_violations
    return {
        "ok": False,
        "violations": [v.to_dict() for v in violations],
        "summary": _summarize(violations),
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
