"""Local lint CLI for the lite-mode Stop hook.

The MCP ``finalize`` server is absent in lite mode, so the Stop hook runs
this CLI directly on the assistant message instead. Because it executes
outside the model loop, it contributes **zero output tokens** — the whole
point of lite mode.

Usage
-----
- ``python -m ja_output_harness.rules_cli --check <file>``
- ``python -m ja_output_harness.rules_cli --check -``  (stdin)
- ``python -m ja_output_harness.rules_cli --check <file>
    --append-lite <state-file> --session <id> --mode <lite|strict-lite>``

Output
------
Single JSON object on stdout::

    {
      "ok": <bool>,                # True iff no ERROR severity violations
      "violation_count": <int>,
      "rule_counts": {"banned_term": 2, ...},
      "violations": [{"rule": ..., "line": ..., ...}, ...]
    }

When ``--append-lite`` is supplied the same JSON is also persisted via
:func:`metrics.record_lite`, which holds the rotate+lock that prevents
concurrent Stop hooks from interleaving entries on Windows. Append
failures are swallowed inside ``record_lite`` — the JSON on stdout
remains the source of truth for the hook.

Exit 0 always — the hook treats the JSON body as authoritative. Crashing
here would break the user's Codex session.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from ja_output_harness import metrics
from ja_output_harness.rules import lint, load_rules, resolve_user_config_path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RULES_PATH = REPO_ROOT / "config" / "banned_terms.yaml"


def _read_input(source: str) -> str:
    if source == "-":
        return sys.stdin.read()
    return Path(source).read_text(encoding="utf-8")


def _force_utf8() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except Exception:
                pass


def check(text: str) -> dict:
    cfg = load_rules(RULES_PATH, resolve_user_config_path())
    violations = lint(text, cfg)
    errors = [v for v in violations if (v.severity or "ERROR") == "ERROR"]
    return {
        "ok": not errors,
        "violation_count": len(violations),
        "rule_counts": dict(Counter(v.rule for v in violations)),
        "violations": [v.to_dict() for v in violations],
    }


def main(argv: list[str] | None = None) -> int:
    _force_utf8()
    parser = argparse.ArgumentParser(
        prog="ja-output-rules",
        description="Lint a Japanese draft without calling any MCP server.",
    )
    parser.add_argument(
        "--check",
        required=True,
        help="Path to a UTF-8 text file, or '-' to read stdin",
    )
    parser.add_argument(
        "--append-lite",
        dest="append_lite",
        default=None,
        help=(
            "Path to jp-harness-lite.jsonl. When set, persist the lint "
            "result through metrics.record_lite (rotate+lock-aware). "
            "Requires --session and --mode."
        ),
    )
    parser.add_argument(
        "--session",
        default="",
        help="Codex session_id forwarded into the lite jsonl entry.",
    )
    parser.add_argument(
        "--mode",
        default="",
        help="Active harness mode (lite | strict-lite) for the lite jsonl entry.",
    )
    args = parser.parse_args(argv)

    try:
        text = _read_input(args.check)
    except OSError as exc:
        # Hook contract: never crash. Empty violation list + error note.
        print(json.dumps({
            "ok": True,
            "violation_count": 0,
            "rule_counts": {},
            "violations": [],
            "error": f"read failed: {exc}",
        }, ensure_ascii=False))
        return 0

    result = check(text)
    if args.append_lite and args.mode:
        # Hook contract: append failures must not break the JSON contract
        # the caller relies on, so record_lite swallows internally. We
        # additionally guard the call itself against the (very unlikely)
        # case where the import-time path resolution raises.
        try:
            metrics.record_lite(
                session=args.session,
                mode=args.mode,
                ok=bool(result.get("ok")),
                violation_count=int(result.get("violation_count") or 0),
                rule_counts=result.get("rule_counts") or {},
                path=Path(args.append_lite),
            )
        except Exception:
            pass
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
