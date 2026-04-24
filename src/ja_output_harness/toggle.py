"""``ja-output-toggle`` — flip the harness on/off without uninstalling.

The Stop and SessionStart hooks read ``~/.codex/state/jp-harness-mode`` on
every turn. This CLI writes that marker so A/B comparisons between
harness-on and harness-off periods are one command away.

Commands
--------
- ``status``         print current mode and AGENTS.md managed-block state
- ``off [--full]``   save mode to ``.bak`` and set marker to ``off``.
                     ``--full`` also evicts the AGENTS.md managed block to
                     ``~/.codex/AGENTS.md.bak-toggle`` so the raw-model
                     baseline is not contaminated by inline rules
- ``on  [--full]``   restore mode (default ``strict-lite``). ``--full`` also
                     re-inserts the evicted AGENTS.md managed block
- ``set <m>``        set marker explicitly (lite | strict-lite | strict | off)

``--full`` changes require a Codex restart because AGENTS.md is loaded once
at startup; the command prints a reminder.

Typical A/B flow
----------------
1. ``ja-output-toggle off --full`` — raw model, no inline rules
2. restart Codex, use it for a while
3. ``ja-output-toggle on --full`` — harness back on
4. restart Codex, use it for the same length
5. ``ja-output-stats scan-sessions --since A --until B`` for raw-model lint
6. ``ja-output-stats ab-report`` for on-period lint
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

VALID_MODES = ("off", "lite", "strict-lite", "strict")
DEFAULT_RESTORE = "strict-lite"
AGENTS_BEGIN = "<!-- BEGIN ja-output-harness managed block -->"
AGENTS_END = "<!-- END ja-output-harness managed block -->"


def _codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or str(Path.home() / ".codex"))


def _state_dir() -> Path:
    state = _codex_home() / "state"
    state.mkdir(parents=True, exist_ok=True)
    return state


def _mode_files() -> tuple[Path, Path]:
    state = _state_dir()
    return state / "jp-harness-mode", state / "jp-harness-mode.bak"


def _agents_files() -> tuple[Path, Path]:
    home = _codex_home()
    return home / "AGENTS.md", home / "AGENTS.md.bak-toggle"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _write(path: Path, value: str) -> None:
    path.write_text(value.strip() + "\n", encoding="utf-8")


def _extract_agents_block(text: str) -> tuple[str, str] | None:
    """Split AGENTS.md into (remaining, managed_block).

    Returns None if no managed block is present. The managed block includes
    BOTH delimiter lines so we can round-trip it unchanged.
    """
    lines = text.splitlines(keepends=True)
    begin_idx = end_idx = -1
    for i, line in enumerate(lines):
        if line.strip() == AGENTS_BEGIN:
            begin_idx = i
        elif line.strip() == AGENTS_END and begin_idx >= 0:
            end_idx = i
            break
    if begin_idx < 0 or end_idx < 0:
        return None
    block = "".join(lines[begin_idx : end_idx + 1])
    # Also consume a single trailing blank line after END so repeated
    # on/off cycles do not accumulate blank lines.
    trailing = end_idx + 1
    if trailing < len(lines) and lines[trailing].strip() == "":
        trailing += 1
    remaining = "".join(lines[:begin_idx] + lines[trailing:])
    return remaining, block


def _evict_agents_block() -> str:
    """Move AGENTS.md managed block to .bak-toggle. Returns a status string.

    Handles the stale-backup case: if ``.bak-toggle`` already exists but the
    managed block has since reappeared in ``AGENTS.md`` (e.g. the installer
    ran again), still remove it from ``AGENTS.md`` so the raw-model baseline
    is not contaminated. The backup is preserved, not overwritten, so the
    original pre-eviction content is never lost.
    """
    agents, bak = _agents_files()
    if not agents.exists():
        return "AGENTS.md not found; skipped"
    text = agents.read_text(encoding="utf-8")
    split = _extract_agents_block(text)
    if split is None:
        if bak.exists():
            return f"no managed block in AGENTS.md; backup preserved at {bak}"
        return "no managed block in AGENTS.md; skipped"
    remaining, block = split
    if bak.exists():
        agents.write_text(remaining, encoding="utf-8")
        return f"removed re-inserted managed block (backup at {bak} preserved)"
    bak.write_text(block, encoding="utf-8")
    agents.write_text(remaining, encoding="utf-8")
    return f"evicted managed block to {bak}"


def _restore_agents_block() -> str:
    """Re-insert managed block from .bak-toggle. Returns a status string."""
    agents, bak = _agents_files()
    if not bak.exists():
        return "no .bak-toggle to restore; skipped"
    if not agents.exists():
        agents.write_text(bak.read_text(encoding="utf-8"), encoding="utf-8")
        bak.unlink()
        return "restored managed block (AGENTS.md was missing, created)"
    current = agents.read_text(encoding="utf-8")
    if AGENTS_BEGIN in current:
        bak.unlink()
        return "managed block already present; removed stale .bak-toggle"
    block = bak.read_text(encoding="utf-8")
    sep = "" if current.endswith("\n") else "\n"
    agents.write_text(current + sep + "\n" + block, encoding="utf-8")
    bak.unlink()
    return "restored managed block to AGENTS.md"


def _agents_block_present() -> bool:
    agents, _ = _agents_files()
    if not agents.exists():
        return False
    return AGENTS_BEGIN in agents.read_text(encoding="utf-8")


def cmd_status(_args: argparse.Namespace) -> int:
    mode_file, bak_file = _mode_files()
    agents, agents_bak = _agents_files()
    current = _read(mode_file) or "(unset, defaults to strict)"
    print(f"mode: {current}")
    if current == "off":
        saved = _read(bak_file) or "(none)"
        print(f"previous: {saved}  (ja-output-toggle on will restore this)")
    block = "present" if _agents_block_present() else "absent"
    print(f"AGENTS.md managed block: {block}")
    if agents_bak.exists():
        print(f"AGENTS.md .bak-toggle: exists ({agents_bak})")
    return 0


def cmd_off(args: argparse.Namespace) -> int:
    mode_file, bak_file = _mode_files()
    current = _read(mode_file)
    if current == "off":
        print("already off")
    else:
        if current:
            _write(bak_file, current)
        _write(mode_file, "off")
        prev = current or "(default)"
        print(f"harness off  (previous mode: {prev})")
    if getattr(args, "full", False):
        note = _evict_agents_block()
        print(f"AGENTS.md: {note}")
        print("Restart Codex (CLI / App) for AGENTS.md change to take effect.")
    else:
        print("Codex replies now pass through untouched.")
    return 0


def cmd_on(args: argparse.Namespace) -> int:
    mode_file, bak_file = _mode_files()
    current = _read(mode_file)
    if current and current != "off":
        print(f"already on  (mode: {current})")
    else:
        restore = _read(bak_file) or DEFAULT_RESTORE
        if restore not in VALID_MODES or restore == "off":
            restore = DEFAULT_RESTORE
        _write(mode_file, restore)
        print(f"harness on  (mode: {restore})")
    if getattr(args, "full", False):
        note = _restore_agents_block()
        print(f"AGENTS.md: {note}")
        print("Restart Codex (CLI / App) for AGENTS.md change to take effect.")
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
    p_off.add_argument(
        "--full",
        action="store_true",
        help="also evict AGENTS.md managed block (raw-model baseline)",
    )
    p_off.set_defaults(func=cmd_off)

    p_on = sub.add_parser("on", help="re-enable the harness (restore from .bak)")
    p_on.add_argument(
        "--full",
        action="store_true",
        help="also restore AGENTS.md managed block from .bak-toggle",
    )
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
