"""Tests for metrics.record and stats CLI command handlers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from codex_jp_harness import metrics, stats


def test_record_appends_jsonl(tmp_path: Path) -> None:
    target = tmp_path / "m.jsonl"
    metrics.record(
        draft="こんにちは",
        violations_count=0,
        severity_counts={"ERROR": 0, "WARNING": 0, "INFO": 0},
        response={"ok": True},
        elapsed_ms=1.23,
        path=target,
    )
    metrics.record(
        draft="slice を含む違反",
        violations_count=1,
        severity_counts={"ERROR": 1, "WARNING": 0, "INFO": 0},
        response={"ok": False, "violations": [{"term": "slice"}], "summary": "1件"},
        elapsed_ms=2.0,
        path=target,
    )
    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["schema_version"] == "1"
    assert first["draft_chars"] == 5
    assert first["draft_bytes"] == len("こんにちは".encode())
    assert first["violations_count"] == 0
    assert first["severity_counts"] == {"ERROR": 0, "WARNING": 0, "INFO": 0}
    assert first["ok"] is True
    assert first["ts"].endswith("Z")
    second = json.loads(lines[1])
    assert second["ok"] is False
    assert second["violations_count"] == 1
    assert second["severity_counts"]["ERROR"] == 1


def test_record_swallows_io_errors(tmp_path: Path) -> None:
    # Passing a path whose parent cannot be created triggers an exception that
    # record() is required to swallow. On Windows, making a file where a dir
    # is expected forces mkdir(parents=True) to fail.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir", encoding="utf-8")
    bad = blocker / "child" / "m.jsonl"
    metrics.record(
        draft="hello",
        violations_count=0,
        severity_counts={},
        response={"ok": True},
        elapsed_ms=0.1,
        path=bad,
    )  # must not raise


def _seed_metrics(target: Path, entries: list[dict]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def test_cmd_show_prints_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "state" / "jp-harness-metrics.jsonl"
    _seed_metrics(
        target,
        [
            {
                "schema_version": "1",
                "ts": "2026-04-20T10:00:00Z",
                "draft_chars": 100,
                "draft_bytes": 300,
                "violations_count": 0,
                "severity_counts": {"ERROR": 0, "WARNING": 0, "INFO": 0},
                "response_bytes": 10,
                "elapsed_ms": 1.0,
                "ok": True,
            },
            {
                "schema_version": "1",
                "ts": "2026-04-20T10:00:03Z",
                "draft_chars": 200,
                "draft_bytes": 600,
                "violations_count": 2,
                "severity_counts": {"ERROR": 1, "WARNING": 1, "INFO": 0},
                "response_bytes": 120,
                "elapsed_ms": 2.5,
                "ok": False,
            },
        ],
    )
    monkeypatch.setattr(stats, "metrics_path", lambda: target)
    rc = stats.cmd_show(argparse.Namespace())
    out = capsys.readouterr().out
    assert rc == 0
    assert "total calls:  2" in out
    assert "ok=true:" in out
    assert "sum(draft_chars) = 300" in out


def test_cmd_overhead_groups_by_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "state" / "jp-harness-metrics.jsonl"
    _seed_metrics(
        target,
        [
            # Turn 1: two calls within window (retry)
            {"ts": "2026-04-20T10:00:00Z", "draft_chars": 100, "violations_count": 2,
             "severity_counts": {"ERROR": 2}, "elapsed_ms": 1.0, "ok": False, "response_bytes": 0,
             "schema_version": "1", "draft_bytes": 0},
            {"ts": "2026-04-20T10:00:04Z", "draft_chars": 100, "violations_count": 0,
             "severity_counts": {}, "elapsed_ms": 1.0, "ok": True, "response_bytes": 0,
             "schema_version": "1", "draft_bytes": 0},
            # Turn 2: single call
            {"ts": "2026-04-20T10:05:00Z", "draft_chars": 80, "violations_count": 0,
             "severity_counts": {}, "elapsed_ms": 1.0, "ok": True, "response_bytes": 0,
             "schema_version": "1", "draft_bytes": 0},
        ],
    )
    monkeypatch.setattr(stats, "metrics_path", lambda: target)
    ns = argparse.Namespace(window=30.0)
    rc = stats.cmd_overhead(ns)
    out = capsys.readouterr().out
    assert rc == 0
    assert "bursts (estimated turns): 2" in out
    assert "total calls:              3" in out
    assert "retries:                  1" in out


def test_cmd_tail_prints_last_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "state" / "jp-harness-metrics.jsonl"
    _seed_metrics(
        target,
        [
            {"ts": f"2026-04-20T10:00:{i:02d}Z", "draft_chars": i, "violations_count": 0,
             "severity_counts": {}, "elapsed_ms": 0.1, "ok": True, "response_bytes": 0,
             "schema_version": "1", "draft_bytes": 0}
            for i in range(5)
        ],
    )
    monkeypatch.setattr(stats, "metrics_path", lambda: target)
    rc = stats.cmd_tail(argparse.Namespace(n=2))
    out = capsys.readouterr().out.splitlines()
    assert rc == 0
    assert len(out) == 2
    assert json.loads(out[-1])["draft_chars"] == 4


def test_cmd_show_empty_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "missing.jsonl"
    monkeypatch.setattr(stats, "metrics_path", lambda: target)
    rc = stats.cmd_show(argparse.Namespace())
    err = capsys.readouterr().err
    assert rc == 1
    assert "No metrics" in err
