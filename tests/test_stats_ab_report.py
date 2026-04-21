"""Tests for ``ja-output-stats ab-report``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from ja_output_harness import stats


def _seed_lite(target: Path, entries: list[dict]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def _lite_entry(ts: str, *, ok: bool, rules: dict | None = None) -> dict:
    return {
        "schema_version": "1",
        "ts": ts,
        "session": "abc",
        "ok": ok,
        "violation_count": 0 if ok else sum((rules or {}).values()),
        "rule_counts": rules or {},
        "mode": "lite",
        "expires": "2099-01-01T00:00:00Z",
    }


def _ns(**kw: object) -> argparse.Namespace:
    return argparse.Namespace(**kw)


def test_wilson_95_boundary_cases() -> None:
    assert stats._wilson_95(0, 0) == (0.0, 0.0)
    lo, hi = stats._wilson_95(1, 1)
    # All successes, n=1 — upper bound at 1.0, lower bound strictly positive.
    assert 0.0 < lo < 1.0
    assert hi == pytest.approx(1.0)
    lo10, hi10 = stats._wilson_95(7, 10)
    assert 0.0 < lo10 < 0.7 < hi10 < 1.0


def test_parse_date_range_valid() -> None:
    start, end = stats._parse_date_range("2026-04-14:2026-04-20")
    assert start.isoformat() == "2026-04-14T00:00:00+00:00"
    # End is exclusive, bumped by one day to include the full final date.
    assert end.isoformat() == "2026-04-21T00:00:00+00:00"


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "2026-04-14",
        "2026-04-14:",
        ":2026-04-20",
        "not-a-date:2026-04-20",
        "2026-04-20:2026-04-14",
    ],
)
def test_parse_date_range_invalid(bad: str) -> None:
    with pytest.raises(ValueError):
        stats._parse_date_range(bad)


def test_ab_report_happy_path_lite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "state" / "jp-harness-lite.jsonl"
    entries = (
        # Baseline: 14-20 April. 4/10 ok = 40% (below 50%).
        [_lite_entry("2026-04-14T10:00:00Z", ok=True)]
        + [_lite_entry("2026-04-15T10:00:00Z", ok=True)]
        + [_lite_entry("2026-04-16T10:00:00Z", ok=True)]
        + [_lite_entry("2026-04-17T10:00:00Z", ok=True)]
        + [
            _lite_entry("2026-04-18T10:00:00Z", ok=False, rules={"banned_term": 2})
            for _ in range(3)
        ]
        + [
            _lite_entry("2026-04-19T10:00:00Z", ok=False, rules={"bare_identifier": 1})
            for _ in range(3)
        ]
        # Test: 21-27 April. 9/10 ok = 90%.
        + [_lite_entry(f"2026-04-21T{i:02d}:00:00Z", ok=True) for i in range(9)]
        + [_lite_entry("2026-04-22T10:00:00Z", ok=False, rules={"banned_term": 1})]
    )
    _seed_lite(target, entries)
    monkeypatch.setattr(stats, "lite_metrics_path", lambda: target)

    rc = stats.cmd_ab_report(
        _ns(baseline="2026-04-14:2026-04-20", test="2026-04-21:2026-04-27", source="lite")
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "source:  lite" in out
    assert "Baseline" in out and "Test" in out
    assert "n=10" in out  # both buckets have 10
    assert "40.0%" in out
    assert "90.0%" in out
    assert "Delta (test - baseline): +50.0 pp" in out
    assert "DECISION" in out
    assert "lite default OK to ship" in out


def test_ab_report_metrics_source_reads_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """metrics source must read archive + active for historical coverage."""
    active = tmp_path / "state" / "jp-harness-metrics.jsonl"
    active.parent.mkdir(parents=True, exist_ok=True)

    # Archive entry in baseline window.
    archive = active.with_name("jp-harness-metrics.1.jsonl")
    archive.write_text(
        json.dumps({"ts": "2026-04-14T10:00:00Z", "ok": True, "rule_counts": {}}) + "\n",
        encoding="utf-8",
    )
    # Active entry in test window.
    active.write_text(
        json.dumps({"ts": "2026-04-21T10:00:00Z", "ok": False, "rule_counts": {"x": 1}}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(stats, "metrics_path", lambda: active)

    rc = stats.cmd_ab_report(
        _ns(baseline="2026-04-14:2026-04-20", test="2026-04-21:2026-04-27", source="metrics")
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "source:  metrics" in out
    # Baseline came from archive, test from active.
    assert "100.0%" in out  # baseline 1/1 ok
    assert "0.0%" in out  # test 0/1 ok


def test_ab_report_empty_ranges_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "state" / "jp-harness-lite.jsonl"
    _seed_lite(target, [_lite_entry("2025-01-01T00:00:00Z", ok=True)])
    monkeypatch.setattr(stats, "lite_metrics_path", lambda: target)

    rc = stats.cmd_ab_report(
        _ns(baseline="2026-04-14:2026-04-20", test="2026-04-21:2026-04-27", source="lite")
    )
    err = capsys.readouterr().err
    assert rc == 1
    assert "No entries in either range" in err


def test_ab_report_invalid_range_returns_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "state" / "jp-harness-lite.jsonl"
    _seed_lite(target, [])
    monkeypatch.setattr(stats, "lite_metrics_path", lambda: target)

    rc = stats.cmd_ab_report(
        _ns(baseline="not-a-range", test="2026-04-21:2026-04-27", source="lite")
    )
    err = capsys.readouterr().err
    assert rc == 2
    assert "error:" in err


def test_ab_report_decision_thresholds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Decision label follows the dogfood-measure.py thresholds (50% / 70%)."""
    target = tmp_path / "state" / "jp-harness-lite.jsonl"
    # Baseline: one ok entry (for range validity). Test: 6 ok / 10 = 60%.
    entries = [_lite_entry("2026-04-14T00:00:00Z", ok=True)]
    entries += [_lite_entry(f"2026-04-21T{i:02d}:00:00Z", ok=True) for i in range(6)]
    entries += [_lite_entry(f"2026-04-21T{i:02d}:00:00Z", ok=False) for i in range(10, 14)]
    _seed_lite(target, entries)
    monkeypatch.setattr(stats, "lite_metrics_path", lambda: target)

    rc = stats.cmd_ab_report(
        _ns(baseline="2026-04-14:2026-04-20", test="2026-04-21:2026-04-27", source="lite")
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "consider strict-lite default" in out
    # n=10 < 20 triggers the wide-CI note? No, note fires at n < 20.
    assert "NOTE:" in out


def test_ab_report_wide_ci_overlap_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "state" / "jp-harness-lite.jsonl"
    # Very small buckets with identical ok rates — CIs will overlap.
    entries = [_lite_entry("2026-04-14T00:00:00Z", ok=True) for _ in range(3)]
    entries += [_lite_entry("2026-04-21T00:00:00Z", ok=True) for _ in range(3)]
    _seed_lite(target, entries)
    monkeypatch.setattr(stats, "lite_metrics_path", lambda: target)

    rc = stats.cmd_ab_report(
        _ns(baseline="2026-04-14:2026-04-20", test="2026-04-21:2026-04-27", source="lite")
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "95% CIs overlap" in out


def test_ab_report_cli_entry_point(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Smoke test: main() parses argv and dispatches to ab-report."""
    target = tmp_path / "state" / "jp-harness-lite.jsonl"
    _seed_lite(
        target,
        [
            _lite_entry("2026-04-14T00:00:00Z", ok=True),
            _lite_entry("2026-04-21T00:00:00Z", ok=False, rules={"banned_term": 1}),
        ],
    )
    monkeypatch.setattr(stats, "lite_metrics_path", lambda: target)

    rc = stats.main(
        [
            "ab-report",
            "--baseline",
            "2026-04-14:2026-04-20",
            "--test",
            "2026-04-21:2026-04-27",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "Baseline" in out and "Test" in out
