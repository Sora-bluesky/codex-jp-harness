"""``ja-output-stats`` — summarize the finalize metrics jsonl.

Reads ``$CODEX_HOME/state/jp-harness-metrics.jsonl`` written by
``server.py`` and prints aggregates. Used to quantify real token /
latency overhead of the MCP finalize gate against baseline rather
than relying on design-time estimates.

Commands
--------
- ``path``      print the metrics jsonl path
- ``show``      distribution of draft size, violations, elapsed time
- ``overhead``  estimate same-turn retry overhead from time-clustered entries
- ``tail N``    show the last N raw entries (for spot checks)
"""

from __future__ import annotations

import argparse
import datetime
import json
import statistics
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

from ja_output_harness.metrics import archive_path, metrics_path


def _iter_file(path: Path) -> Iterator[dict]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def _read_entries(path: Path) -> Iterator[dict]:
    """Yield entries from the archive (older) then the active file (newer).

    Reading both preserves chronological order and avoids losing the rotated
    history from ``ja-output-stats show`` / ``overhead``.
    """
    archive = archive_path(path)
    yield from _iter_file(archive)
    yield from _iter_file(path)


def _percentiles(values: list[float], ps: Iterable[float]) -> dict[str, float]:
    if not values:
        return {f"p{int(p * 100)}": 0.0 for p in ps}
    sorted_vals = sorted(values)
    out: dict[str, float] = {}
    for p in ps:
        idx = max(0, min(len(sorted_vals) - 1, int(round(p * (len(sorted_vals) - 1)))))
        out[f"p{int(p * 100)}"] = float(sorted_vals[idx])
    return out


def cmd_path(args: argparse.Namespace) -> int:
    print(str(metrics_path()))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    path = metrics_path()
    entries = list(_read_entries(path))
    if not entries:
        print(f"No metrics at {path}", file=sys.stderr)
        return 1
    drafts = [int(e.get("draft_chars", 0)) for e in entries]
    violations = [int(e.get("violations_count", 0)) for e in entries]
    elapsed = [float(e.get("elapsed_ms", 0.0)) for e in entries]
    ok_count = sum(1 for e in entries if e.get("ok"))

    total = len(entries)
    fail = total - ok_count
    fixed_count = sum(1 for e in entries if e.get("fixed"))
    print(f"metrics file: {path}")
    print(f"total calls:  {total}")
    print(f"ok=true:      {ok_count} ({ok_count * 100 / total:.1f}%)")
    print(f"ok=false:     {fail} ({fail * 100 / total:.1f}%)")
    fixed_pct = fixed_count * 100 / total
    print(f"fast-path:    {fixed_count} ({fixed_pct:.1f}% server-side auto-rewrite)")
    print()

    def _stats(name: str, vals: list[float], unit: str) -> None:
        if not vals:
            return
        pcts = _percentiles(vals, (0.5, 0.9, 0.99))
        print(
            f"{name:<18}  mean={statistics.mean(vals):>8.1f} {unit}  "
            f"median={pcts['p50']:>8.1f}  p90={pcts['p90']:>8.1f}  p99={pcts['p99']:>8.1f}  "
            f"max={max(vals):>8.1f}"
        )

    _stats("draft_chars", drafts, "chars")
    _stats("violations", violations, "per call")
    _stats("elapsed_ms", elapsed, "ms")
    print()

    total_draft_chars = sum(drafts)
    print(f"sum(draft_chars) = {total_draft_chars}")
    print(
        "theoretical output overhead lower bound: "
        f"{total_draft_chars} chars emitted via tool-call argument "
        "(duplicates the final response body when ok=true)."
    )

    # Rule distribution + fast-path miss diagnosis (schema v2+).
    from collections import Counter

    rule_totals: Counter[str] = Counter()
    miss_rules: Counter[str] = Counter()
    miss_entries = 0
    for e in entries:
        rc = e.get("rule_counts") or {}
        if not isinstance(rc, dict):
            continue
        for rule, n in rc.items():
            try:
                rule_totals[str(rule)] += int(n)
            except (TypeError, ValueError):
                continue
        # A fast-path miss is: ERRORs present AND server did not auto-rewrite.
        # In that case rule_counts reveals which rule(s) made the violation
        # set non-auto-fixable (banned_term without replacement) or left
        # residual ERRORs after rewrite.
        err = int((e.get("severity_counts") or {}).get("ERROR", 0))
        if err > 0 and not e.get("fixed") and rc:
            miss_entries += 1
            for rule, n in rc.items():
                try:
                    miss_rules[str(rule)] += int(n)
                except (TypeError, ValueError):
                    continue

    if rule_totals:
        print()
        print("rule distribution (all entries):")
        width = max(len(r) for r in rule_totals) + 2
        for rule, count in rule_totals.most_common():
            print(f"  {rule:<{width}} {count}")

    if miss_entries:
        print()
        print(f"fast-path miss diagnosis ({miss_entries} entries with ERROR but no auto-rewrite):")
        width = max(len(r) for r in miss_rules) + 2
        for rule, count in miss_rules.most_common():
            print(f"  {rule:<{width}} {count}")
    return 0


def _parse_ts(ts: str) -> datetime.datetime | None:
    try:
        return datetime.datetime.strptime(ts.replace("Z", "+00:00"), "%Y-%m-%dT%H:%M:%S%z")
    except Exception:
        return None


def cmd_overhead(args: argparse.Namespace) -> int:
    """Estimate same-turn retry overhead.

    Heuristic: consecutive calls within ``--window`` seconds are assumed to
    be retries of the same Codex turn. Count retries per burst and report:
    - average burst length (= 1 + retries)
    - distribution of bursts by length
    - estimated output-token overhead vs a 1-call baseline
    """
    path = metrics_path()
    entries = [e for e in _read_entries(path) if _parse_ts(e.get("ts", "")) is not None]
    if not entries:
        print(f"No metrics at {path}", file=sys.stderr)
        return 1
    entries.sort(key=lambda e: _parse_ts(e["ts"]))  # type: ignore[arg-type, return-value]
    window = float(args.window)
    bursts: list[list[dict]] = []
    current: list[dict] = []
    last_ts: datetime.datetime | None = None
    for e in entries:
        ts = _parse_ts(e["ts"])
        if ts is None:
            continue
        if last_ts is not None and (ts - last_ts).total_seconds() > window:
            if current:
                bursts.append(current)
            current = []
        current.append(e)
        last_ts = ts
    if current:
        bursts.append(current)

    from collections import Counter

    lengths = [len(b) for b in bursts]
    dist = Counter(lengths)
    avg = statistics.mean(lengths) if lengths else 0.0
    total_calls = sum(lengths)
    retries = sum(max(0, n - 1) for n in lengths)
    retry_rate = retries / len(bursts) if bursts else 0.0

    print(f"metrics file: {path}")
    print(f"window:       {window}s (consecutive calls within this window = same turn)")
    print(f"bursts (estimated turns): {len(bursts)}")
    print(f"total calls:              {total_calls}")
    print(f"retries:                  {retries}")
    print(f"avg calls per turn:       {avg:.2f}")
    print(f"avg retries per turn:     {retry_rate:.2f}")
    print()
    print("burst length distribution (calls per turn):")
    for n in sorted(dist):
        bar = "#" * min(50, dist[n])
        print(f"  {n:>2} call(s): {dist[n]:>4}  {bar}")
    print()
    print("Estimated output-token overhead vs no-finalize baseline:")
    print(
        "  draft-text is emitted once per tool-call argument AND once as final "
        "assistant message. So output ≈ (retries+2) × draft per turn."
    )
    if bursts:
        baseline = 1.0  # final assistant message only
        with_finalize = retry_rate + 2.0
        pct = (with_finalize - baseline) / baseline * 100
        print(
            f"  avg output-factor: {with_finalize:.2f}× baseline  "
            f"(= +{pct:.0f}% output tokens over naive 1× baseline)"
        )
    return 0


def cmd_tail(args: argparse.Namespace) -> int:
    path = metrics_path()
    entries = list(_read_entries(path))
    if not entries:
        print(f"No metrics at {path}", file=sys.stderr)
        return 1
    n = max(1, int(args.n))
    for e in entries[-n:]:
        print(json.dumps(e, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ja-output-stats",
        description="Summarize finalize() metrics jsonl.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("path", help="print metrics jsonl path").set_defaults(func=cmd_path)
    sub.add_parser("show", help="distribution of draft size, violations, elapsed").set_defaults(
        func=cmd_show
    )
    oh = sub.add_parser("overhead", help="estimate same-turn retry overhead")
    oh.add_argument(
        "--window",
        default=30.0,
        type=float,
        help="Seconds between consecutive calls that are still the same turn (default 30).",
    )
    oh.set_defaults(func=cmd_overhead)
    t = sub.add_parser("tail", help="print the last N entries")
    t.add_argument("n", nargs="?", default=10, type=int, help="N (default 10)")
    t.set_defaults(func=cmd_tail)
    return parser


def _force_utf8_stdout() -> None:
    """Reconfigure stdout to UTF-8 so non-ASCII glyphs (≈, ×, 日本語) print on
    Windows consoles whose default codepage is cp932. Silent no-op on older
    Python / non-reconfigurable streams.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfig = getattr(stream, "reconfigure", None)
        if reconfig is not None:
            try:
                reconfig(encoding="utf-8")
            except Exception:
                pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
