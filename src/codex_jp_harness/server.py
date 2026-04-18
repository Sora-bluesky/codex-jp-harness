"""MCP server exposing the `finalize` tool for Codex CLI.

Codex calls `mcp__jp_lint__finalize(draft)` before delivering a Japanese
technical report. If violations are found, Codex is expected to rewrite
and call again until `ok: true` is returned.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from codex_jp_harness.rules import Violation, lint, load_rules

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
    cfg = load_rules(RULES_PATH)
    violations = lint(draft, cfg)
    error_violations = [v for v in violations if (v.severity or "ERROR") == "ERROR"]
    if not error_violations:
        if not violations:
            return {"ok": True}
        # Only WARNING/INFO remain — pass but surface advisories.
        return {
            "ok": True,
            "advisories": [v.to_dict() for v in violations],
            "summary": _summarize(violations),
        }
    return {
        "ok": False,
        "violations": [v.to_dict() for v in violations],
        "summary": _summarize(violations),
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
