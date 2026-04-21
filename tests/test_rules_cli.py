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
