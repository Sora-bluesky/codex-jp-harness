"""Tests for ``ja-output-stats scan-sessions``.

Covers the Codex rollout parser, timestamp filters, output jsonl export,
and non-Japanese skipping — the pieces that let users A/B compare
raw-model output (after ``ja-output-toggle off --full``) against the
on-harness stream in ``jp-harness-lite.jsonl``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ja_output_harness import stats


def _write_rollout(
    path: Path,
    session_id: str,
    turns: list[tuple[str, str]],
) -> None:
    """Write a minimal rollout jsonl: one session_meta row + N assistant turns.

    ``turns`` is a list of ``(timestamp, text)`` pairs.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = [
        {
            "timestamp": turns[0][0] if turns else "2026-04-24T00:00:00.000Z",
            "type": "session_meta",
            "payload": {"id": session_id},
        }
    ]
    for ts, text in turns:
        rows.append(
            {
                "timestamp": ts,
                "type": "response_item",
                "payload": {
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": text}],
                },
            }
        )
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


@pytest.fixture
def sessions_root(tmp_path: Path) -> Path:
    root = tmp_path / "sessions"
    root.mkdir()
    return root


class TestBasicScan:
    def test_counts_japanese_turns_only(self, sessions_root: Path, capsys):
        _write_rollout(
            sessions_root / "rollout-a.jsonl",
            "sess-a",
            [
                ("2026-04-24T01:00:00.000Z", "これは日本語の応答です。"),
                ("2026-04-24T01:01:00.000Z", "pure english reply, no jp"),
                ("2026-04-24T01:02:00.000Z", "もう一度日本語で返します。"),
            ],
        )
        rc = stats.main(["scan-sessions", "--dir", str(sessions_root)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "assistant Japanese turns:     2" in out
        assert "skipped (non-Japanese turns): 1" in out
        assert "sessions:      1" in out

    def test_fails_when_no_rollouts_found(self, tmp_path: Path, capsys):
        rc = stats.main(["scan-sessions", "--dir", str(tmp_path / "empty")])
        assert rc == 1
        err = capsys.readouterr().err
        assert "no rollout files" in err


class TestTimestampFilter:
    def test_since_excludes_earlier_turns(self, sessions_root: Path, capsys):
        _write_rollout(
            sessions_root / "rollout-a.jsonl",
            "sess-a",
            [
                ("2026-04-24T00:00:00.000Z", "早い日本語応答。"),
                ("2026-04-24T12:00:00.000Z", "遅い日本語応答。"),
            ],
        )
        rc = stats.main(
            [
                "scan-sessions",
                "--dir",
                str(sessions_root),
                "--since",
                "2026-04-24T06:00:00+00:00",
            ]
        )
        out = capsys.readouterr().out
        assert rc == 0
        assert "assistant Japanese turns:     1" in out

    def test_until_excludes_later_turns(self, sessions_root: Path, capsys):
        _write_rollout(
            sessions_root / "rollout-a.jsonl",
            "sess-a",
            [
                ("2026-04-24T00:00:00.000Z", "早い日本語応答。"),
                ("2026-04-24T12:00:00.000Z", "遅い日本語応答。"),
            ],
        )
        rc = stats.main(
            [
                "scan-sessions",
                "--dir",
                str(sessions_root),
                "--until",
                "2026-04-24T06:00:00+00:00",
            ]
        )
        out = capsys.readouterr().out
        assert rc == 0
        assert "assistant Japanese turns:     1" in out

    def test_date_filter_excludes_untimestamped_turns(
        self, sessions_root: Path, capsys
    ):
        """Turns without a parseable timestamp must NOT bypass a dated scan,
        otherwise older rollouts pollute the A/B bucket.
        """
        path = sessions_root / "rollout-mixed.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        # session_meta with id + one assistant row with a VALID timestamp
        # inside the window + one assistant row with NO timestamp field at all.
        rows = [
            {
                "timestamp": "2026-04-24T01:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "sess-mix"},
            },
            {
                "timestamp": "2026-04-24T10:00:00.000Z",
                "type": "response_item",
                "payload": {
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": "タイムスタンプ付きの応答です。"}
                    ],
                },
            },
            {
                # No timestamp → must be skipped when --since / --until is set.
                "type": "response_item",
                "payload": {
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": "タイムスタンプ無しの応答です。"}
                    ],
                },
            },
        ]
        path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
            encoding="utf-8",
        )
        rc = stats.main(
            [
                "scan-sessions",
                "--dir",
                str(sessions_root),
                "--since",
                "2026-04-24T06:00:00+00:00",
            ]
        )
        out = capsys.readouterr().out
        assert rc == 0
        # Only the timestamped turn should count.
        assert "assistant Japanese turns:     1" in out

    def test_no_filter_keeps_untimestamped_turns(
        self, sessions_root: Path, capsys
    ):
        """When no date filter is active, ts=None rows should still be counted
        so casual `scan-sessions` without --since/--until keeps working.
        """
        path = sessions_root / "rollout-no-ts.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "timestamp": "2026-04-24T01:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "sess-x"},
            },
            {
                "type": "response_item",
                "payload": {
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": "時刻なしでも検品はする。"}
                    ],
                },
            },
        ]
        path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
            encoding="utf-8",
        )
        rc = stats.main(["scan-sessions", "--dir", str(sessions_root)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "assistant Japanese turns:     1" in out

    def test_date_only_range_covers_full_utc_day(self, sessions_root: Path, capsys):
        """`--since D --until D` (same date, date-only) must include turns
        throughout the whole day, not just the midnight boundary.
        """
        _write_rollout(
            sessions_root / "rollout-day.jsonl",
            "sess-day",
            [
                ("2026-04-24T00:00:30.000Z", "早朝の応答。"),
                ("2026-04-24T12:30:00.000Z", "昼の応答。"),
                ("2026-04-24T23:45:00.000Z", "深夜の応答。"),
                ("2026-04-25T00:00:05.000Z", "翌日の応答。"),
            ],
        )
        rc = stats.main(
            [
                "scan-sessions",
                "--dir",
                str(sessions_root),
                "--since",
                "2026-04-24",
                "--until",
                "2026-04-24",
            ]
        )
        out = capsys.readouterr().out
        assert rc == 0
        # Three turns inside 2026-04-24 UTC, one on the next day excluded.
        assert "assistant Japanese turns:     3" in out

    def test_invalid_since_fails(self, sessions_root: Path, capsys):
        _write_rollout(
            sessions_root / "rollout-a.jsonl",
            "sess-a",
            [("2026-04-24T00:00:00.000Z", "日本語。")],
        )
        rc = stats.main(
            ["scan-sessions", "--dir", str(sessions_root), "--since", "bogus"]
        )
        assert rc == 2
        err = capsys.readouterr().err
        assert "--since" in err


class TestOutputJsonl:
    def test_writes_lite_compatible_rows(self, sessions_root: Path, tmp_path: Path):
        # 1 clean turn + 1 violating turn
        _write_rollout(
            sessions_root / "rollout-a.jsonl",
            "sess-out",
            [
                ("2026-04-24T01:00:00.000Z", "短く日本語で返します。"),
                (
                    "2026-04-24T01:05:00.000Z",
                    # mixes a bare identifier (slice) to force a violation
                    "slice を進めました。",
                ),
            ],
        )
        out_path = tmp_path / "out.jsonl"
        rc = stats.main(
            [
                "scan-sessions",
                "--dir",
                str(sessions_root),
                "--output-jsonl",
                str(out_path),
            ]
        )
        assert rc == 0
        rows = [
            json.loads(line)
            for line in out_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(rows) == 2
        for row in rows:
            assert row["schema_version"] == "1"
            assert row["mode"] == "scan-sessions"
            assert row["session"] == "sess-out"
            assert "rule_counts" in row
            assert isinstance(row["ok"], bool)
        # Exactly one violating row.
        assert sum(1 for r in rows if r["ok"]) == 1
        assert sum(1 for r in rows if not r["ok"]) == 1
        # Exported ts must be ab-report compatible (no fractional seconds,
        # trailing Z) so ja-output-stats ab-report --source lite can consume
        # the same stream as jp-harness-lite.jsonl.
        for row in rows:
            assert row["ts"].endswith("Z")
            parsed = stats._parse_ts(row["ts"])
            assert parsed is not None, f"ab-report cannot parse ts={row['ts']!r}"


class TestEmptyScanRefreshesOutput:
    def test_empty_scan_overwrites_stale_output_jsonl(
        self, sessions_root: Path, tmp_path: Path
    ):
        """If a previous scan wrote output-jsonl and the next scan has no
        Japanese turns inside the filter window, the stale rows must be
        cleared so later A/B checks do not see old data.
        """
        _write_rollout(
            sessions_root / "rollout-a.jsonl",
            "sess-a",
            [("2026-04-24T01:00:00.000Z", "古い日本語応答。")],
        )
        out_path = tmp_path / "out.jsonl"
        # First scan: populates out_path.
        rc = stats.main(
            [
                "scan-sessions",
                "--dir",
                str(sessions_root),
                "--output-jsonl",
                str(out_path),
            ]
        )
        assert rc == 0
        assert out_path.read_text(encoding="utf-8").strip() != ""
        # Second scan: narrow window excludes all turns; out_path must be
        # rewritten empty so ab-report doesn't read stale rows.
        rc = stats.main(
            [
                "scan-sessions",
                "--dir",
                str(sessions_root),
                "--since",
                "2099-01-01",
                "--until",
                "2099-01-02",
                "--output-jsonl",
                str(out_path),
            ]
        )
        assert rc == 0
        assert out_path.read_text(encoding="utf-8") == ""


class TestMalformedInput:
    def test_skips_corrupt_lines(self, sessions_root: Path, capsys):
        path = sessions_root / "rollout-a.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "timestamp": "2026-04-24T01:00:00.000Z",
                            "type": "session_meta",
                            "payload": {"id": "sess-x"},
                        }
                    ),
                    "{ this is not json",  # garbage line, should be skipped
                    json.dumps(
                        {
                            "timestamp": "2026-04-24T01:01:00.000Z",
                            "type": "response_item",
                            "payload": {
                                "role": "assistant",
                                "content": [
                                    {"type": "output_text", "text": "日本語の応答。"}
                                ],
                            },
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        rc = stats.main(["scan-sessions", "--dir", str(sessions_root)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "assistant Japanese turns:     1" in out

    def test_single_file_path_as_dir(self, sessions_root: Path, capsys):
        """--dir accepts a single rollout file path, not just a directory."""
        path = sessions_root / "rollout-one.jsonl"
        _write_rollout(
            path,
            "sess-one",
            [("2026-04-24T01:00:00.000Z", "単一ファイルのテスト。")],
        )
        rc = stats.main(["scan-sessions", "--dir", str(path)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "assistant Japanese turns:     1" in out
