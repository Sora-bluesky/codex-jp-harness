"""Tests for user-local override merging in load_rules."""

from __future__ import annotations

from pathlib import Path

import pytest

from codex_jp_harness.rules import load_rules, resolve_user_config_path

RULES_PATH = Path(__file__).resolve().parent.parent / "config" / "banned_terms.yaml"


@pytest.fixture
def write_user_yaml(tmp_path: Path):
    def _write(body: str) -> Path:
        p = tmp_path / "jp_lint.yaml"
        p.write_text(body, encoding="utf-8")
        return p

    return _write


class TestResolveUserConfigPath:
    def test_env_override(self, monkeypatch, tmp_path):
        custom = tmp_path / "custom.yaml"
        monkeypatch.setenv("CODEX_JP_HARNESS_USER_CONFIG", str(custom))
        assert resolve_user_config_path() == custom

    def test_xdg_when_env_missing(self, monkeypatch, tmp_path):
        monkeypatch.delenv("CODEX_JP_HARNESS_USER_CONFIG", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        got = resolve_user_config_path()
        assert got == tmp_path / "codex-jp-harness" / "jp_lint.yaml"

    def test_default_home_codex(self, monkeypatch):
        monkeypatch.delenv("CODEX_JP_HARNESS_USER_CONFIG", raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        got = resolve_user_config_path()
        assert got.name == "jp_lint.yaml"
        assert got.parent.name == ".codex"


class TestLoadRulesWithoutUser:
    def test_nonexistent_user_path_ignored(self, tmp_path):
        missing = tmp_path / "does-not-exist.yaml"
        cfg = load_rules(RULES_PATH, missing)
        # Baseline: rc1 ships with 26 banned entries.
        assert len(cfg.banned) == 26

    def test_none_user_path_behaves_as_bundled(self):
        cfg_bundled = load_rules(RULES_PATH)
        cfg_none = load_rules(RULES_PATH, None)
        assert len(cfg_bundled.banned) == len(cfg_none.banned)


class TestDisable:
    def test_disable_removes_bundled_term(self, write_user_yaml):
        user = write_user_yaml("disable: [slice, done]\n")
        cfg = load_rules(RULES_PATH, user)
        terms = {e.get("term") for e in cfg.banned}
        assert "slice" not in terms
        assert "done" not in terms

    def test_disable_unknown_term_is_noop(self, write_user_yaml):
        user = write_user_yaml("disable: [not-a-real-term]\n")
        cfg = load_rules(RULES_PATH, user)
        assert len(cfg.banned) == 26


class TestOverrides:
    def test_override_severity(self, write_user_yaml):
        user = write_user_yaml(
            "overrides:\n  slice:\n    severity: WARNING\n"
        )
        cfg = load_rules(RULES_PATH, user)
        slice_entry = next(e for e in cfg.banned if e["term"] == "slice")
        assert slice_entry["severity"] == "WARNING"

    def test_override_suggest(self, write_user_yaml):
        user = write_user_yaml(
            "overrides:\n  slice:\n    suggest: 今回のスコープ\n"
        )
        cfg = load_rules(RULES_PATH, user)
        slice_entry = next(e for e in cfg.banned if e["term"] == "slice")
        assert slice_entry["suggest"] == "今回のスコープ"
        # Severity still inherits from bundled config.
        assert slice_entry["severity"] == "ERROR"


class TestAdd:
    def test_add_new_term(self, write_user_yaml):
        user = write_user_yaml(
            "add:\n  - term: ddd\n    suggest: ドメイン駆動設計\n    severity: INFO\n"
        )
        cfg = load_rules(RULES_PATH, user)
        assert any(e["term"] == "ddd" for e in cfg.banned)
        ddd = next(e for e in cfg.banned if e["term"] == "ddd")
        assert ddd["severity"] == "INFO"

    def test_add_entry_without_term_is_skipped(self, write_user_yaml):
        user = write_user_yaml("add:\n  - suggest: no-term\n")
        cfg = load_rules(RULES_PATH, user)
        assert len(cfg.banned) == 26


class TestThresholds:
    def test_override_identifier_limit(self, write_user_yaml):
        user = write_user_yaml("thresholds:\n  identifier_limit_per_sentence: 5\n")
        cfg = load_rules(RULES_PATH, user)
        assert cfg.identifier_limit_per_sentence == 5

    def test_override_sentence_length(self, write_user_yaml):
        user = write_user_yaml(
            "thresholds:\n  sentence_length:\n    max_chars: 120\n"
        )
        cfg = load_rules(RULES_PATH, user)
        assert cfg.sentence_max_chars == 120
        # unspecified fields retain bundled defaults
        assert cfg.sentence_length_enabled is True


class TestCombinedOverrides:
    def test_disable_plus_add(self, write_user_yaml):
        user = write_user_yaml(
            "disable: [slice]\n"
            "add:\n"
            "  - term: custom-word\n"
            "    suggest: カスタム用語\n"
            "    severity: WARNING\n"
        )
        cfg = load_rules(RULES_PATH, user)
        terms = {e["term"] for e in cfg.banned}
        assert "slice" not in terms
        assert "custom-word" in terms

    def test_empty_user_file_is_safe(self, write_user_yaml):
        user = write_user_yaml("")
        cfg = load_rules(RULES_PATH, user)
        assert len(cfg.banned) == 26
