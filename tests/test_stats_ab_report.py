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
    defaults: dict[str, object] = {
        "allow_overlap": False,
        "exclude_session": "",
        "source_path": "",
    }
    defaults.update(kw)
    return argparse.Namespace(**defaults)


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
    """Baseline 25 @ 40%, test 25 @ 96% → Wilson lower bound clears 70%."""
    target = tmp_path / "state" / "jp-harness-lite.jsonl"
    entries = (
        # Baseline: 10 ok + 15 fail = 40%. Wilson lower ≈ 23% (below 50%).
        [_lite_entry(f"2026-04-14T{i:02d}:00:00Z", ok=True) for i in range(10)]
        + [
            _lite_entry(f"2026-04-18T{i:02d}:00:00Z", ok=False, rules={"banned_term": 2})
            for i in range(15)
        ]
        # Test: 24 ok + 1 fail = 96%. Wilson lower ≈ 80% (clears 70%).
        + [_lite_entry(f"2026-04-21T{i:02d}:00:00Z", ok=True) for i in range(24)]
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
    assert "n=25" in out
    assert "40.0%" in out
    assert "96.0%" in out
    assert "Delta (test - baseline): +56.0 pp" in out
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


def test_ab_report_lite_source_reads_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """v0.4.2: lite source must also read archive + active.

    record_lite() now rotates jp-harness-lite.jsonl at the same 20 MB
    boundary as metrics. Reading only the active file would silently
    drop pre-rotation history once the file rolls over (gpt-5.4 review
    v0.4.2 MEDIUM #1).
    """
    active = tmp_path / "state" / "jp-harness-lite.jsonl"
    active.parent.mkdir(parents=True, exist_ok=True)

    archive = active.with_name("jp-harness-lite.1.jsonl")
    archive.write_text(
        json.dumps(_lite_entry("2026-04-14T10:00:00Z", ok=True)) + "\n",
        encoding="utf-8",
    )
    active.write_text(
        json.dumps(_lite_entry("2026-04-21T10:00:00Z", ok=False, rules={"banned_term": 1}))
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(stats, "lite_metrics_path", lambda: active)

    rc = stats.cmd_ab_report(
        _ns(baseline="2026-04-14:2026-04-20", test="2026-04-21:2026-04-27", source="lite")
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "source:  lite" in out
    assert "100.0%" in out  # baseline came from archive
    assert "0.0%" in out  # test came from active


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


def test_ab_report_decision_strict_lite_band(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """n=25 @ 80% ok → Wilson lower ≈ 60%, inside the strict-lite band."""
    target = tmp_path / "state" / "jp-harness-lite.jsonl"
    entries = [_lite_entry(f"2026-04-14T{i:02d}:00:00Z", ok=True) for i in range(20)]
    entries += [_lite_entry(f"2026-04-21T{i:02d}:00:00Z", ok=True) for i in range(20)]
    entries += [_lite_entry(f"2026-04-22T{i:02d}:00:00Z", ok=False) for i in range(5)]
    _seed_lite(target, entries)
    monkeypatch.setattr(stats, "lite_metrics_path", lambda: target)

    rc = stats.cmd_ab_report(
        _ns(baseline="2026-04-14:2026-04-20", test="2026-04-21:2026-04-27", source="lite")
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "consider strict-lite default" in out


def test_ab_report_tiny_sample_is_inconclusive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """n=1 with ok=True used to print 'OK to ship'; must now say inconclusive."""
    target = tmp_path / "state" / "jp-harness-lite.jsonl"
    _seed_lite(
        target,
        [
            _lite_entry("2026-04-14T00:00:00Z", ok=True),
            _lite_entry("2026-04-21T00:00:00Z", ok=True),
        ],
    )
    monkeypatch.setattr(stats, "lite_metrics_path", lambda: target)

    rc = stats.cmd_ab_report(
        _ns(baseline="2026-04-14:2026-04-20", test="2026-04-21:2026-04-27", source="lite")
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "inconclusive" in out
    assert "OK to ship" not in out


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
    assert "Wilson 95% CIs overlap" in out


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


def test_ab_report_rejects_overlapping_ranges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "state" / "jp-harness-lite.jsonl"
    _seed_lite(target, [_lite_entry("2026-04-15T00:00:00Z", ok=True)])
    monkeypatch.setattr(stats, "lite_metrics_path", lambda: target)

    rc = stats.cmd_ab_report(
        _ns(baseline="2026-04-14:2026-04-18", test="2026-04-16:2026-04-20", source="lite")
    )
    err = capsys.readouterr().err
    assert rc == 2
    assert "overlap" in err


def test_ab_report_allow_overlap_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--allow-overlap lets ranges share dates; the same entry counts in both."""
    target = tmp_path / "state" / "jp-harness-lite.jsonl"
    _seed_lite(target, [_lite_entry("2026-04-16T00:00:00Z", ok=True)])
    monkeypatch.setattr(stats, "lite_metrics_path", lambda: target)

    rc = stats.cmd_ab_report(
        _ns(
            baseline="2026-04-14:2026-04-18",
            test="2026-04-16:2026-04-20",
            source="lite",
            allow_overlap=True,
        )
    )
    out = capsys.readouterr().out
    assert rc == 0
    # Entry falls into both buckets because of --allow-overlap.
    assert "Baseline" in out and "Test" in out


def test_ab_report_default_excludes_diag_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A manual hook run writes session='diag'; it must not sway small buckets."""
    target = tmp_path / "state" / "jp-harness-lite.jsonl"
    diag = _lite_entry("2026-04-21T10:00:00Z", ok=True)
    diag["session"] = "diag"
    real = _lite_entry("2026-04-21T11:00:00Z", ok=False, rules={"banned_term": 1})
    _seed_lite(
        target,
        [
            _lite_entry("2026-04-14T00:00:00Z", ok=True),
            diag,
            real,
        ],
    )
    monkeypatch.setattr(stats, "lite_metrics_path", lambda: target)

    rc = stats.cmd_ab_report(
        _ns(baseline="2026-04-14:2026-04-20", test="2026-04-21:2026-04-27", source="lite")
    )
    out = capsys.readouterr().out
    assert rc == 0
    # Only the real entry remains in the test bucket.
    assert "n=1" in out
    assert "excluded sessions: diag" in out
    assert "skipped: session=1" in out


def test_ab_report_custom_exclude_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "state" / "jp-harness-lite.jsonl"
    bad = _lite_entry("2026-04-21T10:00:00Z", ok=True)
    bad["session"] = "smoke-test"
    real = _lite_entry("2026-04-21T11:00:00Z", ok=False)
    _seed_lite(target, [_lite_entry("2026-04-14T00:00:00Z", ok=True), bad, real])
    monkeypatch.setattr(stats, "lite_metrics_path", lambda: target)

    rc = stats.cmd_ab_report(
        _ns(
            baseline="2026-04-14:2026-04-20",
            test="2026-04-21:2026-04-27",
            source="lite",
            exclude_session="smoke-test",
        )
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "smoke-test" in out
    assert "diag" in out  # default still included
    assert "n=1" in out


def test_ab_report_counts_malformed_ts_in_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "state" / "jp-harness-lite.jsonl"
    good = _lite_entry("2026-04-21T10:00:00Z", ok=True)
    malformed = {"schema_version": "1", "ts": "not-a-ts", "ok": True, "session": "x"}
    _seed_lite(target, [_lite_entry("2026-04-14T00:00:00Z", ok=True), good, malformed])
    monkeypatch.setattr(stats, "lite_metrics_path", lambda: target)

    rc = stats.cmd_ab_report(
        _ns(baseline="2026-04-14:2026-04-20", test="2026-04-21:2026-04-27", source="lite")
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "unparseable ts=1" in out


def test_ab_report_one_empty_bucket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Baseline has data, test is empty → exit 0 with 'Test empty' note."""
    target = tmp_path / "state" / "jp-harness-lite.jsonl"
    _seed_lite(target, [_lite_entry("2026-04-14T00:00:00Z", ok=True)])
    monkeypatch.setattr(stats, "lite_metrics_path", lambda: target)

    rc = stats.cmd_ab_report(
        _ns(baseline="2026-04-14:2026-04-20", test="2026-04-21:2026-04-27", source="lite")
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "Test empty" in out
    assert "DECISION" not in out


def test_ab_report_source_path_overrides_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--source-path`` reads an ad-hoc jsonl (e.g. ``scan-sessions
    --output-jsonl``) instead of the live lite metrics, so raw-model
    baselines can be compared without overwriting the live stream.
    """
    # Live file must NOT be read when --source-path is set; seed it with a
    # sentinel so a regression (default path still winning) is visible.
    live = tmp_path / "state" / "jp-harness-lite.jsonl"
    _seed_lite(live, [_lite_entry("2026-04-14T00:00:00Z", ok=False, rules={"LIVE": 9})])
    monkeypatch.setattr(stats, "lite_metrics_path", lambda: live)

    # Scan export: all three turns clean, in the baseline window.
    exported = tmp_path / "scan.jsonl"
    _seed_lite(
        exported,
        [
            _lite_entry("2026-04-14T10:00:00Z", ok=True),
            _lite_entry("2026-04-15T11:00:00Z", ok=True),
            _lite_entry("2026-04-16T12:00:00Z", ok=True),
        ],
    )
    rc = stats.cmd_ab_report(
        _ns(
            baseline="2026-04-14:2026-04-20",
            test="2026-04-21:2026-04-27",
            source="lite",
            source_path=str(exported),
        )
    )
    out = capsys.readouterr().out
    assert rc == 0
    # Must reflect the exported baseline (3 clean rows), NOT the live sentinel.
    assert "LIVE" not in out
    # Baseline rate comes from exported file: 3/3 ok.
    assert "100.0%" in out
