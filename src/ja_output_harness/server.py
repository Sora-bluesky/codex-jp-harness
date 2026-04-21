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

from ja_output_harness import metrics
from ja_output_harness.rules import (
    RuleConfig,
    Violation,
    apply_auto_fix,
    apply_backtick_fix,
    extract_replacement,
    lint,
    load_rules,
    resolve_user_config_path,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RULES_PATH = REPO_ROOT / "config" / "banned_terms.yaml"

mcp = FastMCP("jp_lint")


# `finalize` is the hot path — Codex calls it at least once per assistant
# turn, sometimes multiple times. YAML parsing for the bundled + user rules
# dominates per-call I/O. Cache by (path, mtime) so we re-parse only when
# the rule files actually change (gpt-5.4 review #55).
_RULES_CACHE: dict[str, Any] = {"key": None, "cfg": None}


def _load_rules_cached(bundled: Path, user: Path) -> RuleConfig:
    try:
        bundled_mtime = bundled.stat().st_mtime_ns
    except OSError:
        bundled_mtime = None
    try:
        user_mtime = user.stat().st_mtime_ns if user.exists() else None
    except OSError:
        user_mtime = None
    key = (str(bundled), bundled_mtime, str(user), user_mtime)
    if _RULES_CACHE["key"] == key and _RULES_CACHE["cfg"] is not None:
        return _RULES_CACHE["cfg"]
    cfg = load_rules(bundled, user)
    _RULES_CACHE["key"] = key
    _RULES_CACHE["cfg"] = cfg
    return cfg


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
    cfg = _load_rules_cached(RULES_PATH, resolve_user_config_path())
    violations = lint(draft, cfg)
    error_violations = [v for v in violations if (v.severity or "ERROR") == "ERROR"]
    severity_counts = Counter(v.severity or "ERROR" for v in violations)
    fixed = False
    response: dict[str, Any]

    if error_violations and _fast_path_applicable(error_violations):
        rewritten, fix_summary = _apply_fast_path_fixes(draft, cfg, error_violations)
        if rewritten != draft:
            new_violations = lint(rewritten, cfg)
            new_errors = [v for v in new_violations if (v.severity or "ERROR") == "ERROR"]
            if not new_errors:
                response = {
                    "ok": True,
                    "fixed": True,
                    "rewritten": rewritten,
                    "summary": fix_summary,
                }
                if new_violations:
                    response["advisories"] = [v.to_dict() for v in new_violations]
                fixed = True
                violations = new_violations
                severity_counts = Counter(v.severity or "ERROR" for v in violations)
            else:
                # Auto-fix left residual ERRORs — fall back to the regular loop.
                response = _build_standard_response(violations, error_violations)
        else:
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


_AUTO_FIX_RULES = frozenset({
    "banned_term",
    "bare_identifier",
    "pr_issue_number",
    "too_many_identifiers",
    "sentence_too_long",
})


def _fast_path_applicable(error_violations: list[Violation]) -> bool:
    """Return True when every ERROR has a deterministic server-side fix candidate.

    - ``banned_term`` is fixable when the suggest yields a replacement.
    - ``bare_identifier`` / ``pr_issue_number`` are always fixable by wrapping
      in backticks.
    - ``too_many_identifiers`` / ``sentence_too_long`` often clear as a side
      effect of backticking bare identifiers, so we still try the fast path
      and re-lint decides whether the fix stuck.
    """
    if not error_violations:
        return False
    for v in error_violations:
        if v.rule == "banned_term":
            if not extract_replacement(v.suggest):
                return False
            continue
        if v.rule in _AUTO_FIX_RULES:
            continue
        return False
    return True


def _apply_fast_path_fixes(
    draft: str, cfg: Any, error_violations: list[Violation]
) -> tuple[str, str]:
    """Apply banned-term substitutions and backtick wrapping.

    Returns ``(rewritten, summary)``. ``summary`` is the human-readable
    description placed on the fast-path response. ``apply_backtick_fix``
    wraps both generic bare identifiers and PR/issue references in one pass,
    so we count them together here.
    """
    banned = [
        v for v in error_violations
        if v.rule == "banned_term" and extract_replacement(v.suggest)
    ]
    wrap_targets = [
        v for v in error_violations
        if v.rule in ("bare_identifier", "pr_issue_number")
    ]

    rewritten = draft
    parts: list[str] = []
    if banned:
        rewritten = apply_auto_fix(rewritten, banned)
        parts.extend(f"{v.term} → {extract_replacement(v.suggest)}" for v in banned)
    if wrap_targets:
        rewritten = apply_backtick_fix(rewritten, cfg)
        parts.append(f"識別子/参照 {len(wrap_targets)} 件をバッククォート化")

    fix_count = len(banned) + (1 if wrap_targets else 0)
    summary = f"{fix_count}件を自動修正 ({', '.join(parts)})" if parts else "変更なし"
    return rewritten, summary


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
