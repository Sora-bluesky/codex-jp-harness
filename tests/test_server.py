"""Tests for codex_jp_harness.server."""

from codex_jp_harness.rules import Violation
from codex_jp_harness.server import _summarize, finalize


class TestSummarize:
    def test_empty(self):
        assert _summarize([]) == "0件の違反を検出 ()"

    def test_only_error(self):
        violations = [
            Violation(rule="banned_term", line=1, term="x", severity="ERROR"),
            Violation(rule="banned_term", line=2, term="y", severity="ERROR"),
        ]
        s = _summarize(violations)
        assert "2件の違反を検出" in s
        assert "2 ERROR" in s

    def test_mixed_severities(self):
        violations = [
            Violation(rule="banned_term", line=1, term="a", severity="ERROR"),
            Violation(rule="banned_term", line=2, term="b", severity="WARNING"),
            Violation(rule="banned_term", line=3, term="c", severity="WARNING"),
            Violation(rule="banned_term", line=4, term="d", severity="INFO"),
        ]
        s = _summarize(violations)
        assert "4件の違反を検出" in s
        assert "1 ERROR" in s
        assert "2 WARNING" in s
        assert "1 INFO" in s

    def test_default_severity_treated_as_error(self):
        v = Violation(rule="banned_term", line=1, term="x")
        s = _summarize([v])
        assert "1 ERROR" in s


class TestFinalize:
    def test_clean_draft_passes(self):
        result = finalize("進捗を報告します。実装が完了しました。")
        assert result == {"ok": True}

    def test_error_violations_block(self):
        # `done` is severity=ERROR
        result = finalize("TASK を done に切り替えた。")
        assert result["ok"] is False
        assert "violations" in result
        assert any(v.get("term") == "done" for v in result["violations"])

    def test_warning_only_passes_with_advisories(self):
        # `helper` is severity=WARNING; if no ERROR, ok should be True
        # but advisories should be returned. We craft a sentence short
        # enough to avoid sentence_too_long (which is implicit ERROR).
        result = finalize("helper を切り出した。")
        assert result["ok"] is True
        assert "advisories" in result
        assert any(v.get("term") == "helper" for v in result["advisories"])

    def test_info_only_passes_with_advisories(self):
        # `merge` is severity=INFO
        result = finalize("merge を実施。")
        assert result["ok"] is True
        assert "advisories" in result
        assert any(v.get("term") == "merge" for v in result["advisories"])

    def test_mixed_error_and_warning_blocks(self):
        # Mix of done (ERROR) and helper (WARNING) — should block on ERROR.
        result = finalize("done に変更し、helper を整理した。")
        assert result["ok"] is False
        terms = {v.get("term") for v in result["violations"]}
        assert "done" in terms
        assert "helper" in terms
