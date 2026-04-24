"""``ja-output-toggle`` — flip the harness on/off without uninstalling.

The Stop and SessionStart hooks read ``~/.codex/state/jp-harness-mode`` on
every turn. This CLI writes that marker so A/B comparisons between
harness-on and harness-off periods are one command away.

Commands
--------
- ``status``   print current mode (and saved previous mode when off)
- ``off``      save current mode to ``.bak`` and set marker to ``off``
- ``on``       restore mode from ``.bak`` (fallback: ``strict-lite``)
- ``set <m>``  set marker explicitly (lite | strict-lite | strict | off)

Typical A/B flow
----------------
1. ``ja-output-toggle off`` and use Codex for a while
2. ``ja-output-toggle on`` and use Codex for a similar window
3. ``ja-output-stats ab-report --baseline <off-range> --test <on-range>``
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

VALID_MODES = ("off", "lite", "strict-lite", "strict")
DEFAULT_RESTORE = "strict-lite"


def _state_dir() -> Path:
    codex_home = os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")
    state = Path(codex_home) / "state"
    state.mkdir(parents=True, exist_ok=True)
    return state


def _mode_files() -> tuple[Path, Path]:
    state = _state_dir()
    return state / "jp-harness-mode", state / "jp-harness-mode.bak"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _write(path: Path, value: str) -> None:
    path.write_text(value.strip() + "\n", encoding="utf-8")


def cmd_status(_args: argparse.Namespace) -> int:
    mode_file, bak_file = _mode_files()
    current = _read(mode_file) or "(unset, defaults to strict)"
    print(f"mode: {current}")
    if current == "off":
        saved = _read(bak_file) or "(none)"
        print(f"previous: {saved}  (ja-output-toggle on will restore this)")
    return 0


def cmd_off(_args: argparse.Namespace) -> int:
    mode_file, bak_file = _mode_files()
    current = _read(mode_file)
    if current == "off":
        print("already off")
        return 0
    if current:
        _write(bak_file, current)
    _write(mode_file, "off")
    prev = current or "(default)"
    print(f"harness off  (previous mode: {prev})")
    print("Codex replies now pass through untouched.")
    return 0


def cmd_on(_args: argparse.Namespace) -> int:
    mode_file, bak_file = _mode_files()
    current = _read(mode_file)
    if current and current != "off":
        print(f"already on  (mode: {current})")
        return 0
    restore = _read(bak_file) or DEFAULT_RESTORE
    if restore not in VALID_MODES or restore == "off":
        restore = DEFAULT_RESTORE
    _write(mode_file, restore)
    print(f"harness on  (mode: {restore})")
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    mode = args.mode.strip()
    if mode not in VALID_MODES:
        print(
            f"invalid mode: {mode!r}. valid: {', '.join(VALID_MODES)}",
            file=sys.stderr,
        )
        return 2
    mode_file, bak_file = _mode_files()
    current = _read(mode_file)
    if current and current != mode and current != "off":
        _write(bak_file, current)
    _write(mode_file, mode)
    print(f"mode: {mode}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ja-output-toggle",
        description=(
            "Turn the ja-output-harness on/off without uninstalling, so you "
            "can A/B compare harness-on vs harness-off runs."
        ),
    )
    sub = parser.add_subparsers(dest="cmd")

    p_status = sub.add_parser("status", help="print current mode")
    p_status.set_defaults(func=cmd_status)

    p_off = sub.add_parser("off", help="disable the harness")
    p_off.set_defaults(func=cmd_off)

    p_on = sub.add_parser("on", help="re-enable the harness (restore from .bak)")
    p_on.set_defaults(func=cmd_on)

    p_set = sub.add_parser("set", help="set mode explicitly")
    p_set.add_argument("mode", choices=list(VALID_MODES))
    p_set.set_defaults(func=cmd_set)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
