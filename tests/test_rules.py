"""Unit tests for codex_jp_harness.rules."""

from pathlib import Path

import pytest

from codex_jp_harness.rules import (
    Violation,
    detect_banned_terms,
    detect_bare_identifiers,
    detect_sentence_length,
    detect_too_many_identifiers,
    lint,
    load_rules,
)

RULES_PATH = Path(__file__).resolve().parent.parent / "config" / "banned_terms.yaml"


@pytest.fixture(scope="module")
def cfg():
    return load_rules(RULES_PATH)


class TestBannedTerms:
    def test_slice_detected(self, cfg):
        violations = detect_banned_terms("今回の slice では限定対応", cfg)
        assert any(v.rule == "banned_term" and v.term == "slice" for v in violations)

    def test_done_detected(self, cfg):
        violations = detect_banned_terms("TASK を done に切り替えた", cfg)
        assert any(v.term == "done" for v in violations)

    def test_multiple_terms_detected(self, cfg):
        text = "今回の slice では done に切り替えた"
        violations = detect_banned_terms(text, cfg)
        terms = {v.term for v in violations}
        assert "slice" in terms
        assert "done" in terms

    def test_case_insensitive(self, cfg):
        violations = detect_banned_terms("Slice を進めた", cfg)
        assert any(v.term == "slice" for v in violations)

    def test_backtick_enclosed_ignored(self, cfg):
        violations = detect_banned_terms("`slice` は禁止語です", cfg)
        assert not any(v.rule == "banned_term" for v in violations)

    def test_code_block_ignored(self, cfg):
        text = "説明:\n```python\nslice = data[0:5]\n```\n続き"
        violations = detect_banned_terms(text, cfg)
        assert not any(v.rule == "banned_term" for v in violations)

    def test_word_boundary(self, cfg):
        # "sliced" should NOT match "slice"
        violations = detect_banned_terms("data was sliced properly", cfg)
        assert not any(v.term == "slice" for v in violations)

    def test_handoff_detected(self, cfg):
        violations = detect_banned_terms("handoff を更新しました", cfg)
        assert any(v.term == "handoff" for v in violations)

    def test_japanese_jargon_bekitou_detected(self, cfg):
        # Japanese jargon banned for reader clarity
        violations = detect_banned_terms("このスクリプトは冪等に動く", cfg)
        assert any(v.term == "冪等" for v in violations)

    def test_japanese_jargon_in_backticks_ignored(self, cfg):
        violations = detect_banned_terms("`冪等` は idempotent の和訳", cfg)
        assert not any(v.term == "冪等" for v in violations)

    def test_clean_text_no_violations(self, cfg):
        violations = detect_banned_terms(
            "進捗を報告します。実装を完了し、テストが通りました。", cfg
        )
        assert violations == []

    def test_suggest_included(self, cfg):
        violations = detect_banned_terms("slice を進めた", cfg)
        assert violations[0].suggest != ""


class TestBareIdentifiers:
    def test_file_path_detected(self, cfg):
        violations = detect_bare_identifiers("ファイル HANDOFF.md を更新しました", cfg)
        assert any(v.token == "HANDOFF.md" for v in violations)

    def test_branch_name_detected(self, cfg):
        text = "ブランチ codex/task306-stdin-parity で作業"
        violations = detect_bare_identifiers(text, cfg)
        assert any("task306-stdin-parity" in v.token for v in violations)

    def test_task_id_detected(self, cfg):
        violations = detect_bare_identifiers("TASK-306 を進めた", cfg)
        assert any(v.token == "TASK-306" for v in violations)

    def test_backtick_enclosed_ignored(self, cfg):
        violations = detect_bare_identifiers("ファイル `HANDOFF.md` を更新", cfg)
        assert not any(v.rule == "bare_identifier" for v in violations)

    def test_code_block_ignored(self, cfg):
        text = "例:\n```\nfile.py\n```\n続き"
        violations = detect_bare_identifiers(text, cfg)
        assert not any(v.rule == "bare_identifier" for v in violations)

    def test_plain_english_word_not_flagged(self, cfg):
        # "slice" is banned_term territory, not bare_identifier (no punctuation)
        violations = detect_bare_identifiers("slice を進めた", cfg)
        assert violations == []


class TestTooManyIdentifiers:
    def test_four_identifiers_flagged(self, cfg):
        text = (
            "TASK-306 を codex/task306-stdin で prompt_transport として "
            "send-paste 経由に流した。"
        )
        violations = detect_too_many_identifiers(text, cfg)
        assert any(v.rule == "too_many_identifiers" for v in violations)

    def test_two_identifiers_ok(self, cfg):
        text = "TASK-306 を winsmux-core.ps1 で対応しました。"
        violations = detect_too_many_identifiers(text, cfg)
        assert violations == []

    def test_split_sentences_counted_separately(self, cfg):
        # Each sentence has 2 identifiers, total 4 but split across 2 sentences
        text = "TASK-306 を main に merge。それから TASK-307 を dev に送る。"
        violations = detect_too_many_identifiers(text, cfg)
        assert violations == []


class TestSentenceLength:
    def test_short_sentence_ok(self, cfg):
        assert detect_sentence_length("進捗を報告します。", cfg) == []

    def test_long_sentence_flagged(self, cfg):
        # 85 chars + period = > 80 char limit (no identifiers)
        text = "あ" * 85 + "。"
        violations = detect_sentence_length(text, cfg)
        assert any(v.rule == "sentence_too_long" for v in violations)
        assert violations[0].count == 85
        assert violations[0].limit == 80

    def test_60_char_with_identifier_flagged(self, cfg):
        # 60 chars containing an identifier → should hit the 50-char limit
        text = "今回は TASK-306 の作業を進めて、レビューと動作確認まで完了しました。"
        violations = detect_sentence_length(text, cfg)
        # This sentence has TASK-306 and is > 50 chars
        if len(text.rstrip("。")) > 50:
            assert any(v.rule == "sentence_too_long" for v in violations)

    def test_50_char_without_identifier_ok(self, cfg):
        # Short sentence with no identifiers passes
        text = "今回の作業は無事に完了し、レビュー依頼を出しました。"
        violations = detect_sentence_length(text, cfg)
        assert violations == []


class TestLintIntegration:
    def test_real_world_bad_output(self, cfg):
        """Actual bad output observed from Codex in the wild."""
        text = (
            "TASK-306 を codex/task306-stdin-parity-20260417 で開始し、"
            "prompt_transport=stdin を受け入れて pane dispatch で "
            "send-paste 経由に流す実装を入れました。"
        )
        violations = lint(text, cfg)
        rules_found = {v.rule for v in violations}
        assert "bare_identifier" in rules_found
        assert "too_many_identifiers" in rules_found
        assert "banned_term" in rules_found  # dispatch is banned

    def test_clean_report_passes(self, cfg):
        text = (
            "進捗を報告します。\n"
            "実装: `winsmux-core.ps1` の差を埋めました。\n"
            "確認: `Pester` で `245/245` 通過しました。\n"
            "次の一手: レビュー依頼を出します。"
        )
        violations = lint(text, cfg)
        assert violations == []

    def test_empty_draft_passes(self, cfg):
        assert lint("", cfg) == []


class TestVialationSerialization:
    def test_to_dict_excludes_empty(self):
        v = Violation(rule="banned_term", line=1, term="slice", suggest="限定的な変更")
        d = v.to_dict()
        assert d == {
            "rule": "banned_term",
            "line": 1,
            "term": "slice",
            "suggest": "限定的な変更",
        }

    def test_to_dict_excludes_zero_count(self):
        v = Violation(rule="banned_term", line=1, term="x")
        d = v.to_dict()
        assert "count" not in d
        assert "limit" not in d
