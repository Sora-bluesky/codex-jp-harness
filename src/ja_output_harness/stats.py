"""``ja-output-stats`` — summarize the finalize metrics jsonl.

Reads ``$CODEX_HOME/state/jp-harness-metrics.jsonl`` written by
``server.py`` and prints aggregates. Used to quantify real token /
latency overhead of the MCP finalize gate against baseline rather
than relying on design-time estimates.

Commands
--------
- ``path``       print the metrics jsonl path
- ``show``       distribution of draft size, violations, elapsed time
- ``overhead``   estimate same-turn retry overhead from time-clustered entries
- ``tail N``     show the last N raw entries (for spot checks)
- ``ab-report``  compare ok rate between two date ranges with Wilson 95% CI
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import statistics
import sys
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path

from ja_output_harness.metrics import archive_path, lite_metrics_path, metrics_path


def _wilson_95(ok: int, n: int) -> tuple[float, float]:
    """Wilson 95% confidence interval (z=1.96) for a binary proportion.

    Wilson is used instead of normal-approximation because the lite-mode
    dogfood buckets are small (n=20-100) and the true ok rate can sit
    near the boundary (70-95%) where the normal CI misbehaves.
    """
    if n == 0:
        return 0.0, 0.0
    z = 1.96
    p = ok / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


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


def _parse_date_range(s: str) -> tuple[datetime.datetime, datetime.datetime]:
    """Parse ``YYYY-MM-DD:YYYY-MM-DD`` (inclusive both ends, UTC).

    Returns (start_inclusive, end_exclusive). The end date is bumped by
    one day so a caller filtering ``start <= ts < end`` captures the full
    final day.
    """
    parts = s.split(":")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Invalid range '{s}'. Expected YYYY-MM-DD:YYYY-MM-DD.")
    try:
        start = datetime.datetime.strptime(parts[0], "%Y-%m-%d")
        end = datetime.datetime.strptime(parts[1], "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"Invalid date in '{s}'. Use YYYY-MM-DD.") from exc
    if end < start:
        raise ValueError(f"Range end earlier than start: '{s}'.")
    return (
        start.replace(tzinfo=datetime.UTC),
        (end + datetime.timedelta(days=1)).replace(tzinfo=datetime.UTC),
    )


def _summarize(entries: list[dict]) -> dict:
    """Compute ok rate, Wilson CI and aggregated rule_counts for a bucket."""
    n = len(entries)
    ok = sum(1 for e in entries if e.get("ok"))
    lo, hi = _wilson_95(ok, n)
    agg: Counter[str] = Counter()
    for e in entries:
        rc = e.get("rule_counts") or {}
        if not isinstance(rc, dict):
            continue
        for rule, v in rc.items():
            try:
                agg[str(rule)] += int(v)
            except (TypeError, ValueError):
                continue
    return {
        "n": n,
        "ok": ok,
        "rate": (ok / n) if n else 0.0,
        "ci_lo": lo,
        "ci_hi": hi,
        "rule_counts": agg,
    }


def _source_entries(source: str) -> tuple[Path, Iterator[dict]]:
    """Resolve the jsonl path for ``source`` and yield its entries.

    ``metrics`` reads archive + active so rotated history is preserved.
    ``lite`` reads the active file only — the lite jsonl is not rotated
    yet (v0.4.1 will share ``_rotate_lock``).
    """
    if source == "metrics":
        path = metrics_path()
        return path, _read_entries(path)
    if source == "lite":
        path = lite_metrics_path()
        return path, _iter_file(path)
    raise ValueError(f"Unknown source '{source}'. Expected 'lite' or 'metrics'.")


DIAGNOSTIC_SESSIONS = frozenset({"diag"})
MIN_DECIDABLE_N = 20


def _ranges_overlap(
    b_start: datetime.datetime,
    b_end: datetime.datetime,
    t_start: datetime.datetime,
    t_end: datetime.datetime,
) -> bool:
    """Half-open interval overlap: ``[b_start, b_end) ∩ [t_start, t_end)``."""
    return b_start < t_end and t_start < b_end


def _decision_for_bucket(n: int, ci_lo: float) -> str:
    """Return the v0.4.0 dogfood decision label.

    Guards against shipping on small-sample noise by
    (a) requiring ``n >= MIN_DECIDABLE_N``, and
    (b) comparing the Wilson **lower bound** — not the point estimate —
        against the 50% / 70% thresholds. With n=1 and a single success
        the point estimate is 100% but the lower bound is ~2.5%, so the
        decision comes out as "not ready" rather than "OK to ship"
        (gpt-5.4 review v0.4.0 MAJOR #4).
    """
    if n < MIN_DECIDABLE_N:
        return (
            f"inconclusive (n={n} < {MIN_DECIDABLE_N}); collect at least"
            f" {MIN_DECIDABLE_N} samples before deciding."
        )
    if ci_lo >= 0.70:
        return "lite default OK to ship (Wilson lower bound >= 70%)."
    if ci_lo >= 0.50:
        return "consider strict-lite default (Wilson lower bound 50-70%)."
    return "lite default NOT ready; keep strict as default or iterate."


def cmd_ab_report(args: argparse.Namespace) -> int:
    """Compare ok rate between a baseline and a test date range.

    Lifts ``.references/dogfood-measure.py`` into the CLI so v0.4.0 dogfood
    buckets can be split / compared without a scratch script. Works on
    lite jsonl (default) or the strict-mode metrics jsonl via ``--source``.
    """
    try:
        b_start, b_end = _parse_date_range(args.baseline)
        t_start, t_end = _parse_date_range(args.test)
        path, entries_iter = _source_entries(args.source)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if _ranges_overlap(b_start, b_end, t_start, t_end) and not args.allow_overlap:
        print(
            "error: baseline and test ranges overlap; the same entry would be"
            " counted in both buckets. Pass --allow-overlap to force it.",
            file=sys.stderr,
        )
        return 2

    excluded = set(DIAGNOSTIC_SESSIONS)
    if args.exclude_session:
        for s in args.exclude_session.split(","):
            s = s.strip()
            if s:
                excluded.add(s)

    baseline: list[dict] = []
    test: list[dict] = []
    skipped_ts = 0
    skipped_session = 0
    for e in entries_iter:
        if excluded and str(e.get("session", "")) in excluded:
            skipped_session += 1
            continue
        ts = _parse_ts(e.get("ts", ""))
        if ts is None:
            skipped_ts += 1
            continue
        if b_start <= ts < b_end:
            baseline.append(e)
        if t_start <= ts < t_end:
            test.append(e)

    if not baseline and not test:
        print(f"No entries in either range at {path}", file=sys.stderr)
        if skipped_session or skipped_ts:
            print(
                f"  (skipped session={skipped_session}, unparseable ts={skipped_ts})",
                file=sys.stderr,
            )
        return 1

    b = _summarize(baseline)
    t = _summarize(test)

    print(f"source:  {args.source}  ({path})")
    if excluded:
        print(f"excluded sessions: {', '.join(sorted(excluded))}")
    if skipped_session or skipped_ts:
        print(f"skipped: session={skipped_session}, unparseable ts={skipped_ts}")
    print()
    _print_bucket("Baseline", args.baseline, b)
    print()
    _print_bucket("Test    ", args.test, t)
    print()

    if b["n"] == 0:
        print("Baseline empty — cannot compare.")
    elif t["n"] == 0:
        print("Test empty — cannot compare.")
    else:
        delta_pp = (t["rate"] - b["rate"]) * 100
        direction = "higher" if delta_pp > 0 else ("lower" if delta_pp < 0 else "equal")
        print(f"Delta (test - baseline): {delta_pp:+.1f} pp  ({direction})")
        ci_overlap = not (b["ci_hi"] < t["ci_lo"] or t["ci_hi"] < b["ci_lo"])
        if ci_overlap:
            print(
                "CI overlap: Wilson 95% CIs overlap — difference is not"
                " conclusive; collect more samples."
            )
        else:
            print(
                "CI overlap: Wilson 95% CIs do not overlap — descriptive signal"
                " only, not a two-proportion significance test."
            )

        print()
        print(f"DECISION (from test bucket): {_decision_for_bucket(t['n'], t['ci_lo'])}")
    return 0


def _print_bucket(label: str, range_str: str, s: dict) -> None:
    n = s["n"]
    if n == 0:
        print(f"{label} ({range_str}): no entries")
        return
    print(
        f"{label} ({range_str}): n={n}  ok={s['ok']} ({100 * s['rate']:.1f}%)"
        f"  Wilson 95% CI: [{100 * s['ci_lo']:.1f}%, {100 * s['ci_hi']:.1f}%]"
    )
    if s["rule_counts"]:
        width = max(len(r) for r in s["rule_counts"]) + 2
        print("  top rules:")
        for rule, count in s["rule_counts"].most_common(5):
            print(f"    {rule:<{width}} {count}")


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

    ab = sub.add_parser(
        "ab-report",
        help="compare ok rate between two date ranges with Wilson 95% CI",
    )
    ab.add_argument(
        "--baseline",
        required=True,
        metavar="YYYY-MM-DD:YYYY-MM-DD",
        help="Baseline date range (UTC, inclusive both ends).",
    )
    ab.add_argument(
        "--test",
        required=True,
        metavar="YYYY-MM-DD:YYYY-MM-DD",
        help="Test date range (UTC, inclusive both ends).",
    )
    ab.add_argument(
        "--source",
        choices=("lite", "metrics"),
        default="lite",
        help="Which jsonl to read (default: lite — the v0.4.0 dogfood stream).",
    )
    ab.add_argument(
        "--allow-overlap",
        action="store_true",
        help=(
            "Permit baseline and test ranges to overlap. By default overlapping"
            " ranges are rejected because the same entry would be counted in"
            " both buckets."
        ),
    )
    ab.add_argument(
        "--exclude-session",
        default="",
        metavar="ID[,ID...]",
        help=(
            "Comma-separated session IDs to skip in addition to the built-in"
            f" diagnostic set {sorted(DIAGNOSTIC_SESSIONS)}. Useful for removing"
            " synthetic hook invocations from a dogfood bucket."
        ),
    )
    ab.set_defaults(func=cmd_ab_report)
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
