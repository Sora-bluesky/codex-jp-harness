"""Tests for ``ja_output_harness.discover``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from ja_output_harness import tune
from ja_output_harness.discover import (
    DEFAULT_ALLOWLIST,
    Candidate,
    scan_text,
    suggest_for,
)


class TestMultiWordTermExclusion:
    """gpt-5.4 review #53: phrase-level banned terms must not leak as tokens."""

    def test_contract_drift_not_split_into_words(self):
        text = (
            "contract drift を検出した。"
            "contract drift が再発した。"
            "contract drift への対策を練る。"
        )
        cands = scan_text(
            text,
            existing_terms={"contract drift"},
            allowlist=set(),
        )
        terms = {c.term for c in cands}
        assert "contract" not in terms
        assert "drift" not in terms

    def test_multi_word_term_that_does_not_match_leaves_tokens(self):
        text = "drift は単独で何度も出てくる。drift と drift と drift。"
        # existing_terms contains the phrase, but this text does not match
        # the phrase (words appear independently). Drift should still surface.
        cands = scan_text(
            text,
            existing_terms={"contract drift"},
            allowlist=set(),
        )
        assert any(c.term == "drift" for c in cands)


class TestScanText:
    def test_repeated_term_surfaces(self):
        text = "preview を開いた。preview を閉じた。preview をもう一度。"
        cands = scan_text(text, existing_terms=set(), allowlist=set())
        terms = [c.term for c in cands]
        assert "preview" in terms
        preview = next(c for c in cands if c.term == "preview")
        assert preview.count == 3

    def test_below_min_occurrences_filtered(self):
        text = "preview を 1 回だけ触れた。"
        cands = scan_text(text, min_occurrences=2, allowlist=set())
        assert all(c.term != "preview" for c in cands)

    def test_existing_terms_excluded(self):
        text = "slice を外したい。slice を繰り返す。"
        cands = scan_text(text, existing_terms={"slice"}, allowlist=set())
        assert not any(c.term == "slice" for c in cands)

    def test_allowlist_excluded(self):
        text = "API を叩く。API の応答を待つ。"
        cands = scan_text(text, allowlist={"api"})
        assert not any(c.term.lower() == "api" for c in cands)

    def test_inline_backtick_ignored(self):
        text = "`composer` の説明だけ書く。`composer` の実装もある。"
        cands = scan_text(text, allowlist=set())
        # Only backticked mentions → not flagged
        assert not any(c.term == "composer" for c in cands)

    def test_fenced_code_block_ignored(self):
        text = """プロンプトについて書きます。
```
composer_v2
composer_v2
composer_v2
```
本文側に composer が 2 回、composer がもう 1 回。"""
        cands = scan_text(text, allowlist=set())
        # composer appears in plain text 3 times
        comp = next((c for c in cands if c.term == "composer"), None)
        assert comp is not None
        assert comp.count >= 2

    def test_markdown_link_url_ignored(self):
        text = "ドキュメントは [preview](https://example.com/preview) を参照。preview を確認。"
        cands = scan_text(text, allowlist=set())
        preview = next((c for c in cands if c.term == "preview"), None)
        # Link text `preview` counts once; URL portion `preview` must not count.
        # Plus the prose `preview`, so count should be 2 (below min_occurrences=2 boundary).
        if preview:
            assert preview.count == 2

    def test_case_insensitive_aggregation(self):
        text = "Preview を開く。preview を閉じる。PREVIEW をもう一度。"
        cands = scan_text(text, min_occurrences=2, allowlist=set())
        preview = next((c for c in cands if c.term == "preview"), None)
        assert preview is not None
        assert preview.count == 3

    def test_short_tokens_not_surfaced(self):
        # tokens shorter than 3 chars are dropped
        text = "if の後に is が来て in と続く。if の後に is が来て in と続く。"
        cands = scan_text(text, min_occurrences=2, allowlist=set())
        assert all(len(c.term) >= 3 for c in cands)

    def test_sorted_by_count_then_alpha(self):
        text = (
            "alpha を使う。alpha を再利用。alpha もう一度。"
            "bravo を使う。bravo を再利用。"
            "charlie を使う。charlie を再利用。"
        )
        cands = scan_text(text, min_occurrences=2, allowlist=set())
        terms = [c.term for c in cands if c.term in ("alpha", "bravo", "charlie")]
        assert terms == ["alpha", "bravo", "charlie"]  # count 3, 2, 2; then alpha


class TestSuggestFor:
    def test_known_term(self):
        assert "プレビュー" in (suggest_for("preview") or "")

    def test_case_insensitive(self):
        assert suggest_for("Preview") == suggest_for("preview")

    def test_unknown_term_returns_none(self):
        assert suggest_for("zzznotatermever") is None


class TestDefaultAllowlist:
    def test_includes_common_acronyms(self):
        for t in ("api", "http", "json", "ci", "pr", "mcp", "url", "sdk"):
            assert t in DEFAULT_ALLOWLIST

    def test_includes_stdio_streams(self):
        for t in ("stdin", "stdout", "stderr"):
            assert t in DEFAULT_ALLOWLIST

    def test_includes_git_verbs(self):
        for t in ("commit", "push", "pull", "branch", "clone"):
            assert t in DEFAULT_ALLOWLIST

    def test_includes_test_frameworks(self):
        for t in ("pester", "pytest", "jest"):
            assert t in DEFAULT_ALLOWLIST

    def test_includes_unix_tools(self):
        for t in ("grep", "awk", "sed", "curl"):
            assert t in DEFAULT_ALLOWLIST

    def test_no_empty_or_short(self):
        for t in DEFAULT_ALLOWLIST:
            assert len(t) >= 2
            assert t == t.lower()


class TestCmdDiscover:
    def test_tsv_output_from_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ):
        draft = tmp_path / "draft.md"
        draft.write_text(
            "preview を開き、preview を確認し、preview をもう一度開く。",
            encoding="utf-8",
        )
        # Force an empty user override so existing_terms comes from bundled yaml only.
        monkeypatch.setenv(
            "CODEX_JP_HARNESS_USER_CONFIG", str(tmp_path / "does-not-exist.yaml")
        )
        ns = argparse.Namespace(
            file=str(draft),
            stdin=False,
            top=5,
            min_occurrences=2,
            format="tsv",
        )
        rc = tune.cmd_discover(ns)
        assert rc == 0
        out = capsys.readouterr().out.strip()
        assert "preview" in out
        # TSV columns: count \t term \t suggestion \t context
        first = out.splitlines()[0]
        parts = first.split("\t")
        assert parts[0] == "3"
        assert parts[1] == "preview"
        # suggestion should come from SUGGESTION_DICT
        assert "プレビュー" in parts[2]

    def test_json_output_structure(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ):
        draft = tmp_path / "draft.md"
        draft.write_text("iframe を 2 回開く。iframe を閉じる。", encoding="utf-8")
        monkeypatch.setenv(
            "CODEX_JP_HARNESS_USER_CONFIG", str(tmp_path / "does-not-exist.yaml")
        )
        ns = argparse.Namespace(
            file=str(draft), stdin=False, top=0, min_occurrences=2, format="json"
        )
        rc = tune.cmd_discover(ns)
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        iframe = next((d for d in data if d["term"] == "iframe"), None)
        assert iframe is not None
        assert iframe["count"] == 2
        assert "suggested_replacement" in iframe

    def test_no_source_returns_error(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        class _TTY:
            def isatty(self):
                return True

            def read(self):
                return ""

        monkeypatch.setattr("sys.stdin", _TTY())
        ns = argparse.Namespace(
            file=None, stdin=False, top=5, min_occurrences=2, format="tsv"
        )
        rc = tune.cmd_discover(ns)
        assert rc == 2
        err = capsys.readouterr().err
        assert "pass --file" in err


class TestCandidateToDict:
    def test_to_dict_round_trip(self):
        c = Candidate(term="preview", count=3, contexts=["a", "b"])
        d = c.to_dict()
        assert d == {"term": "preview", "count": 3, "contexts": ["a", "b"]}
