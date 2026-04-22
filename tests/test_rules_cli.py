"""Tests for rules_cli — the local lint CLI used by lite-mode Stop hook."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from ja_output_harness import rules_cli


def test_clean_draft_returns_ok(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    draft = tmp_path / "draft.txt"
    draft.write_text("こんにちは。", encoding="utf-8")
    rc = rules_cli.main(["--check", str(draft)])
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert rc == 0
    assert payload["ok"] is True
    assert payload["violation_count"] == 0
    assert payload["rule_counts"] == {}
    assert payload["violations"] == []


def test_banned_term_returns_violation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    draft = tmp_path / "draft.txt"
    draft.write_text("slice を更新した。", encoding="utf-8")
    rules_cli.main(["--check", str(draft)])
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert payload["ok"] is False
    assert payload["violation_count"] == 1
    assert payload["rule_counts"] == {"banned_term": 1}
    assert payload["violations"][0]["term"] == "slice"


def test_multiple_rules_aggregated(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    draft = tmp_path / "draft.txt"
    draft.write_text("slice では src/foo.py を更新した。", encoding="utf-8")
    rules_cli.main(["--check", str(draft)])
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["ok"] is False
    assert payload["rule_counts"] == {"banned_term": 1, "bare_identifier": 1}


def test_stdin_dash_argument(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("slice を更新した。"))
    rules_cli.main(["--check", "-"])
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["ok"] is False
    assert payload["rule_counts"] == {"banned_term": 1}


def test_missing_file_returns_ok_with_error_note(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Hook contract: rules_cli must NOT crash even when asked to read a
    file that does not exist. A corrupted hook should never break the
    user's Codex session.
    """
    rc = rules_cli.main(["--check", str(tmp_path / "does-not-exist.txt")])
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert rc == 0
    assert payload["ok"] is True
    assert payload["violation_count"] == 0
    assert "error" in payload


def test_check_argument_is_required() -> None:
    with pytest.raises(SystemExit):
        rules_cli.main([])


def test_utf8_japanese_roundtrip(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Japanese characters must pass through the CLI intact."""
    draft = tmp_path / "draft.txt"
    draft.write_text("識別子 src/foo.py を含む報告。", encoding="utf-8")
    rules_cli.main(["--check", str(draft)])
    payload = json.loads(capsys.readouterr().out.strip())
    assert "src/foo.py" in payload["violations"][0]["token"]
    assert "識別子" in payload["violations"][0]["snippet"]


def test_append_lite_persists_entry_through_record_lite(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--append-lite must route the lint result through metrics.record_lite,
    which holds the rotate+lock primitives so concurrent Stop hooks on
    Windows cannot interleave entries (v0.4.2 follow-up to gpt-5.4 #51).
    """
    draft = tmp_path / "draft.txt"
    draft.write_text("slice を更新した。", encoding="utf-8")
    state_file = tmp_path / "jp-harness-lite.jsonl"
    rc = rules_cli.main([
        "--check", str(draft),
        "--append-lite", str(state_file),
        "--session", "sess-cli",
        "--mode", "strict-lite",
    ])
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert rc == 0
    # stdout payload still drives the hook's block decision unchanged.
    assert payload["ok"] is False
    assert payload["rule_counts"] == {"banned_term": 1}
    # And the entry was persisted on disk with the lite jsonl schema.
    assert state_file.exists()
    entries = state_file.read_text(encoding="utf-8").splitlines()
    assert len(entries) == 1
    entry = json.loads(entries[0])
    assert entry["session"] == "sess-cli"
    assert entry["mode"] == "strict-lite"
    assert entry["ok"] is False
    assert entry["violation_count"] == 1
    assert entry["rule_counts"] == {"banned_term": 1}


def test_append_lite_skipped_when_mode_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Defensive: callers must supply --mode; otherwise we never write the
    jsonl entry (an empty mode would corrupt downstream ja-output-stats).
    """
    draft = tmp_path / "draft.txt"
    draft.write_text("こんにちは。", encoding="utf-8")
    state_file = tmp_path / "lite.jsonl"
    rc = rules_cli.main([
        "--check", str(draft),
        "--append-lite", str(state_file),
        "--session", "sess",
        # --mode intentionally omitted
    ])
    capsys.readouterr()  # drain stdout
    assert rc == 0
    assert not state_file.exists()
