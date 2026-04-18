"""``codex-jp-tune`` — manage the user-local override of jp_lint rules.

The server loads bundled ``config/banned_terms.yaml`` and, on top of it,
merges a user-local override file (default ``~/.codex/jp_lint.yaml``).
This CLI edits that override file without touching the bundled rules.

Commands
--------
- ``path``                    print resolved override path
- ``show``                    print effective (merged) banned terms
- ``disable <term>``          drop a bundled term from lint
- ``enable <term>``           undo ``disable``
- ``set-severity <term> <L>`` override severity (ERROR/WARNING/INFO)
- ``add <term> --suggest S``  add a project-specific banned term
- ``remove <term>``           remove a previously added term

The override file is loaded line-by-line as YAML. Comments are NOT
preserved on rewrite (PyYAML limitation); users who want to keep rich
structure should hand-edit the file directly.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

from codex_jp_harness.rules import load_rules, resolve_user_config_path

VALID_SEVERITIES = ("ERROR", "WARNING", "INFO")

BUNDLED_RULES_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "banned_terms.yaml"
)


def _load_user(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def _save_user(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def cmd_path(_args: argparse.Namespace) -> int:
    print(resolve_user_config_path())
    return 0


def cmd_show(_args: argparse.Namespace) -> int:
    cfg = load_rules(BUNDLED_RULES_PATH, resolve_user_config_path())
    print(f"# effective banned terms ({len(cfg.banned)} entries)")
    for entry in cfg.banned:
        term = entry.get("term", "")
        sev = entry.get("severity", "ERROR")
        cat = entry.get("category", "")
        sug = entry.get("suggest", "")
        parts = [f"- {term} [{sev}"]
        if cat:
            parts.append(f"/{cat}")
        parts.append("]")
        if sug:
            parts.append(f" {sug}")
        print("".join(parts))
    return 0


def cmd_disable(args: argparse.Namespace) -> int:
    path = resolve_user_config_path()
    data = _load_user(path)
    disabled = list(data.get("disable", []) or [])
    if args.term in disabled:
        print(f"already disabled: {args.term}", file=sys.stderr)
        return 0
    disabled.append(args.term)
    data["disable"] = disabled
    _save_user(path, data)
    print(f"disabled: {args.term}  ({path})")
    return 0


def cmd_enable(args: argparse.Namespace) -> int:
    path = resolve_user_config_path()
    data = _load_user(path)
    disabled = list(data.get("disable", []) or [])
    if args.term not in disabled:
        print(f"not in disable list: {args.term}", file=sys.stderr)
        return 1
    disabled.remove(args.term)
    if disabled:
        data["disable"] = disabled
    else:
        data.pop("disable", None)
    _save_user(path, data)
    print(f"enabled: {args.term}  ({path})")
    return 0


def cmd_set_severity(args: argparse.Namespace) -> int:
    if args.severity not in VALID_SEVERITIES:
        print(
            f"invalid severity: {args.severity} (use one of {'/'.join(VALID_SEVERITIES)})",
            file=sys.stderr,
        )
        return 2
    path = resolve_user_config_path()
    data = _load_user(path)
    overrides = dict(data.get("overrides", {}) or {})
    entry = dict(overrides.get(args.term, {}) or {})
    entry["severity"] = args.severity
    overrides[args.term] = entry
    data["overrides"] = overrides
    _save_user(path, data)
    print(f"{args.term}.severity = {args.severity}  ({path})")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    if args.severity not in VALID_SEVERITIES:
        print(
            f"invalid severity: {args.severity} (use one of {'/'.join(VALID_SEVERITIES)})",
            file=sys.stderr,
        )
        return 2
    path = resolve_user_config_path()
    data = _load_user(path)
    added = list(data.get("add", []) or [])
    if any(e.get("term") == args.term for e in added):
        print(f"already added: {args.term} (use `remove` first to update)", file=sys.stderr)
        return 1
    entry: dict[str, str] = {"term": args.term, "suggest": args.suggest, "severity": args.severity}
    if args.category:
        entry["category"] = args.category
    added.append(entry)
    data["add"] = added
    _save_user(path, data)
    print(f"added: {args.term}  ({path})")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    path = resolve_user_config_path()
    data = _load_user(path)
    added = list(data.get("add", []) or [])
    new_added = [e for e in added if e.get("term") != args.term]
    if len(new_added) == len(added):
        print(f"not in add list: {args.term}", file=sys.stderr)
        return 1
    if new_added:
        data["add"] = new_added
    else:
        data.pop("add", None)
    _save_user(path, data)
    print(f"removed: {args.term}  ({path})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="codex-jp-tune",
        description="Manage user-local overrides for the codex-jp-harness lint rules.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("path", help="print the resolved user override path").set_defaults(
        func=cmd_path
    )
    sub.add_parser("show", help="print effective (merged) banned terms").set_defaults(
        func=cmd_show
    )

    p_disable = sub.add_parser("disable", help="disable a bundled banned term")
    p_disable.add_argument("term")
    p_disable.set_defaults(func=cmd_disable)

    p_enable = sub.add_parser("enable", help="undo disable for a term")
    p_enable.add_argument("term")
    p_enable.set_defaults(func=cmd_enable)

    p_sev = sub.add_parser("set-severity", help="override severity for a term")
    p_sev.add_argument("term")
    p_sev.add_argument("severity", choices=VALID_SEVERITIES)
    p_sev.set_defaults(func=cmd_set_severity)

    p_add = sub.add_parser("add", help="add a user-defined banned term")
    p_add.add_argument("term")
    p_add.add_argument("--suggest", required=True, help="replacement guidance")
    p_add.add_argument(
        "--severity", default="ERROR", choices=VALID_SEVERITIES, help="default: ERROR"
    )
    p_add.add_argument("--category", default="", help="free-form category label")
    p_add.set_defaults(func=cmd_add)

    p_rm = sub.add_parser("remove", help="remove a user-added term")
    p_rm.add_argument("term")
    p_rm.set_defaults(func=cmd_remove)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
