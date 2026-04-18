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

    def test_severity_assigned(self, cfg):
        # All violations should carry a severity (default ERROR)
        violations = detect_banned_terms("slice を進めた", cfg)
        assert violations[0].severity in ("ERROR", "WARNING", "INFO")

    def test_severity_info_for_merge(self, cfg):
        # merge is INFO (katakana well-established)
        violations = detect_banned_terms("main に merge した", cfg)
        merge_v = [v for v in violations if v.term == "merge"]
        assert merge_v and merge_v[0].severity == "INFO"

    def test_severity_warning_for_helper(self, cfg):
        violations = detect_banned_terms("helper 関数を切り出した", cfg)
        helper_v = [v for v in violations if v.term == "helper"]
        assert helper_v and helper_v[0].severity == "WARNING"

    def test_severity_error_for_fallback(self, cfg):
        violations = detect_banned_terms("fallback で対処した", cfg)
        fb_v = [v for v in violations if v.term == "fallback"]
        assert fb_v and fb_v[0].severity == "ERROR"

    def test_new_concepts_detected(self, cfg):
        # All new concepts category terms should be caught
        for term in ("fingerprint", "fallback", "fixture", "payload"):
            violations = detect_banned_terms(f"{term} を確認した", cfg)
            assert any(v.term == term for v in violations), f"{term} not detected"

    def test_new_review_terms_detected(self, cfg):
        for term in ("verdict", "blocker"):
            violations = detect_banned_terms(f"{term} を整理した", cfg)
            assert any(v.term == term for v in violations), f"{term} not detected"

    def test_new_state_terms_detected(self, cfg):
        for term in ("pending", "idle"):
            violations = detect_banned_terms(f"状態は {term} です", cfg)
            assert any(v.term == term for v in violations), f"{term} not detected"

    def test_cherry_pick_with_hyphen_detected(self, cfg):
        violations = detect_banned_terms("cherry-pick で取り込んだ", cfg)
        assert any(v.term == "cherry-pick" for v in violations)

    def test_katakana_form_present_for_kana_words(self, cfg):
        # New-schema entries that have established katakana should expose it
        # via the underlying entry (not yet propagated to Violation, but the
        # config must carry it for tune/reporting).
        terms_with_kana = {"fingerprint", "fallback", "fixture", "payload", "merge"}
        config_terms = {e.get("term"): e for e in cfg.banned}
        for t in terms_with_kana:
            assert config_terms[t].get("katakana_form"), f"{t} missing katakana_form"


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

    def test_markdown_link_url_not_flagged(self, cfg):
        # URLs inside [text](url) markdown links should not trigger
        # bare_identifier (URLs naturally contain . / -).
        text = "詳細は [こちら](https://example.com/path/to/page.html) を参照してください。"
        violations = detect_bare_identifiers(text, cfg)
        assert violations == []

    def test_markdown_link_text_still_scanned(self, cfg):
        # The label part of [text](url) is NOT masked, so identifiers in
        # the label still count.
        text = "詳細は [TASK-101](https://example.com) を参照してください。"
        violations = detect_bare_identifiers(text, cfg)
        assert any(v.token == "TASK-101" for v in violations)


class TestTooManyIdentifiers:
    def test_four_identifiers_flagged(self, cfg):
        text = (
            "TASK-306 を codex/task306-stdin で prompt_transport として "
            "send-paste 経由に流した。"
        )
        violations = detect_too_many_identifiers(text, cfg)
        assert any(v.rule == "too_many_identifiers" for v in violations)

    def test_two_identifiers_ok(self, cfg):
        text = "FAKE-001 を sample-core.ps1 で対応しました。"
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
            "実装: `sample-core.ps1` の差を埋めました。\n"
            "確認: `pytest` で `245/245` 通過しました。\n"
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
        # severity defaults to "ERROR" (not empty), so it's always present.
        assert d == {
            "rule": "banned_term",
            "line": 1,
            "term": "slice",
            "suggest": "限定的な変更",
            "severity": "ERROR",
        }

    def test_to_dict_excludes_zero_count(self):
        v = Violation(rule="banned_term", line=1, term="x")
        d = v.to_dict()
        assert "count" not in d
        assert "limit" not in d

    def test_to_dict_includes_severity(self):
        v = Violation(rule="banned_term", line=1, term="x", severity="WARNING")
        d = v.to_dict()
        assert d["severity"] == "WARNING"

    def test_to_dict_excludes_empty_category(self):
        # category defaults to "" so it should be filtered out
        v = Violation(rule="banned_term", line=1, term="x")
        d = v.to_dict()
        assert "category" not in d
