"""MCP server exposing the `finalize` tool for Codex CLI.

Codex calls `mcp__jp_lint__finalize(draft)` before delivering a Japanese
technical report. If violations are found, Codex is expected to rewrite
and call again until `ok: true` is returned.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from codex_jp_harness.rules import lint, load_rules

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RULES_PATH = REPO_ROOT / "config" / "banned_terms.yaml"

mcp = FastMCP("jp_lint")


@mcp.tool()
def finalize(draft: str) -> dict[str, Any]:
    """日本語技術報告のドラフトを検査する。

    違反があれば修正指示を返し、Codex は指示に従って書き直して再呼び出しする。

    Args:
        draft: 日本語技術報告のドラフト全文

    Returns:
        合格: ``{"ok": True}``
        不合格: ``{"ok": False, "violations": [...], "summary": "N件の違反を検出"}``
    """
    cfg = load_rules(RULES_PATH)
    violations = lint(draft, cfg)
    if not violations:
        return {"ok": True}
    return {
        "ok": False,
        "violations": [v.to_dict() for v in violations],
        "summary": f"{len(violations)}件の違反を検出",
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
