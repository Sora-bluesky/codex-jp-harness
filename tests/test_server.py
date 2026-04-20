"""Tests for codex_jp_harness.server."""

from codex_jp_harness.rules import Violation
from codex_jp_harness.server import _fast_path_applicable, _summarize, finalize


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

    def test_banned_term_error_takes_fast_path(self):
        # `done` is severity=ERROR and banned_term with a short replacement,
        # so the server auto-rewrites rather than returning ok:false.
        result = finalize("TASK を done に切り替えた。")
        assert result["ok"] is True
        assert result.get("fixed") is True
        assert "rewritten" in result
        assert "完了" in result["rewritten"]
        assert "done" not in result["rewritten"].lower()

    def test_non_banned_term_error_stays_in_slow_path(self):
        # `bare_identifier` is never auto-fixable; fast path must not apply.
        result = finalize("foo.bar.baz という処理を走らせた。")
        assert result["ok"] is False
        assert "violations" in result
        assert any(v.get("rule") == "bare_identifier" for v in result["violations"])
        assert result.get("fixed") is not True

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

    def test_mixed_banned_term_error_and_warning_fast_path(self):
        # done (ERROR banned_term) + helper (WARNING banned_term).
        # ERROR is auto-fixable → fast path. helper survives as advisory.
        result = finalize("done に変更し、helper を整理した。")
        assert result["ok"] is True
        assert result.get("fixed") is True
        assert "完了" in result["rewritten"]
        # WARNING helper should be in advisories after the fix, not blocked.
        assert "advisories" in result
        assert any(v.get("term") == "helper" for v in result["advisories"])

    def test_mixed_banned_term_and_structural_error_stays_slow(self):
        # done (ERROR banned_term) + bare_identifier (ERROR, not auto-fixable)
        # means fast path skips entirely — we keep the whole list as violations.
        result = finalize("done に切り替え、foo.bar.baz を走らせた。")
        assert result["ok"] is False
        rules = {v.get("rule") for v in result["violations"]}
        assert "banned_term" in rules
        assert "bare_identifier" in rules
        assert result.get("fixed") is not True


class TestFastPathGate:
    def test_banned_term_with_replacement_applicable(self):
        vs = [
            Violation(
                rule="banned_term", line=1, term="slice",
                suggest="限定的な変更", severity="ERROR",
            )
        ]
        assert _fast_path_applicable(vs) is True

    def test_banned_term_without_replacement_rejected(self):
        vs = [Violation(rule="banned_term", line=1, term="slice", suggest="", severity="ERROR")]
        assert _fast_path_applicable(vs) is False

    def test_non_banned_term_rejected(self):
        vs = [Violation(rule="bare_identifier", line=1, token="foo.bar", severity="ERROR")]
        assert _fast_path_applicable(vs) is False

    def test_empty_rejected(self):
        assert _fast_path_applicable([]) is False

    def test_mixed_rule_types_rejected(self):
        vs = [
            Violation(
                rule="banned_term", line=1, term="slice",
                suggest="限定的な変更", severity="ERROR",
            ),
            Violation(rule="bare_identifier", line=1, token="foo.bar", severity="ERROR"),
        ]
        assert _fast_path_applicable(vs) is False
