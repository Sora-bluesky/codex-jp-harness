"""Tests for the ja-output-tune CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ja_output_harness import tune


@pytest.fixture
def user_config(monkeypatch, tmp_path: Path) -> Path:
    path = tmp_path / "jp_lint.yaml"
    monkeypatch.setenv("CODEX_JP_HARNESS_USER_CONFIG", str(path))
    return path


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class TestPath:
    def test_path_prints_resolved(self, user_config: Path, capsys):
        rc = tune.main(["path"])
        assert rc == 0
        out = capsys.readouterr().out.strip()
        assert out == str(user_config)


class TestDisable:
    def test_disable_creates_entry(self, user_config: Path, capsys):
        rc = tune.main(["disable", "slice"])
        assert rc == 0
        data = _load(user_config)
        assert data["disable"] == ["slice"]

    def test_disable_twice_is_noop(self, user_config: Path, capsys):
        tune.main(["disable", "slice"])
        tune.main(["disable", "slice"])
        data = _load(user_config)
        assert data["disable"] == ["slice"]


class TestEnable:
    def test_enable_removes_entry(self, user_config: Path, capsys):
        tune.main(["disable", "slice"])
        rc = tune.main(["enable", "slice"])
        assert rc == 0
        data = _load(user_config)
        # key removed entirely when list is empty
        assert "disable" not in data

    def test_enable_not_in_list_errors(self, user_config: Path, capsys):
        rc = tune.main(["enable", "never-disabled"])
        assert rc == 1


class TestSetSeverity:
    def test_valid_severity(self, user_config: Path, capsys):
        rc = tune.main(["set-severity", "slice", "WARNING"])
        assert rc == 0
        data = _load(user_config)
        assert data["overrides"]["slice"]["severity"] == "WARNING"

    def test_invalid_severity_rejected(self, user_config: Path, capsys):
        with pytest.raises(SystemExit):
            # argparse choices enforcement
            tune.main(["set-severity", "slice", "CRITICAL"])


class TestAdd:
    def test_add_creates_entry(self, user_config: Path, capsys):
        rc = tune.main(
            ["add", "ddd", "--suggest", "ドメイン駆動設計", "--severity", "INFO"]
        )
        assert rc == 0
        data = _load(user_config)
        assert data["add"][0]["term"] == "ddd"
        assert data["add"][0]["suggest"] == "ドメイン駆動設計"
        assert data["add"][0]["severity"] == "INFO"

    def test_add_duplicate_refused(self, user_config: Path, capsys):
        tune.main(["add", "ddd", "--suggest", "x"])
        rc = tune.main(["add", "ddd", "--suggest", "y"])
        assert rc == 1

    def test_add_with_category(self, user_config: Path):
        tune.main(
            [
                "add",
                "foo",
                "--suggest",
                "バー",
                "--category",
                "project",
            ]
        )
        data = _load(user_config)
        assert data["add"][0]["category"] == "project"


class TestRemove:
    def test_remove_added_term(self, user_config: Path, capsys):
        tune.main(["add", "ddd", "--suggest", "x"])
        rc = tune.main(["remove", "ddd"])
        assert rc == 0
        data = _load(user_config)
        assert "add" not in data

    def test_remove_unknown_errors(self, user_config: Path, capsys):
        rc = tune.main(["remove", "ghost"])
        assert rc == 1


class TestSetSeverityOnAddedTerm:
    """gpt-5.4 review #44: set-severity must reach user-added terms too."""

    def test_severity_on_added_term_is_effective(self, user_config: Path):
        tune.main(["add", "custom-term", "--suggest", "置換案", "--severity", "ERROR"])
        rc = tune.main(["set-severity", "custom-term", "WARNING"])
        assert rc == 0
        data = _load(user_config)
        assert data["overrides"]["custom-term"]["severity"] == "WARNING"

        # Effective severity through load_rules must reflect the override.
        from ja_output_harness.rules import load_rules
        cfg = load_rules(tune.BUNDLED_RULES_PATH, user_config)
        entry = next(e for e in cfg.banned if e.get("term") == "custom-term")
        assert entry["severity"] == "WARNING"

    def test_unknown_term_rejected(self, user_config: Path, capsys):
        rc = tune.main(["set-severity", "no-such-term-anywhere", "WARNING"])
        assert rc == 1
        err = capsys.readouterr().err
        assert "unknown term" in err


class TestAtomicWrite:
    """gpt-5.4 review #48: user override updates must be atomic."""

    def test_save_leaves_no_tempfile(self, user_config: Path):
        tune.main(["add", "persist-me", "--suggest", "永続化"])
        # No stray tempfile siblings should remain (.jp_lint.yaml.*.tmp).
        siblings = list(user_config.parent.glob(f".{user_config.name}.*.tmp"))
        assert siblings == []

    def test_lock_file_released_after_success(self, user_config: Path):
        tune.main(["add", "foo", "--suggest", "バー"])
        lock = user_config.with_suffix(user_config.suffix + ".lock")
        assert not lock.exists()

    def test_concurrent_writes_are_serialized(self, user_config: Path):
        import threading

        terms = [f"term-{i}" for i in range(8)]

        def writer(term: str) -> None:
            tune.main(["add", term, "--suggest", "x"])

        threads = [threading.Thread(target=writer, args=(t,)) for t in terms]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        data = _load(user_config)
        added_terms = {e["term"] for e in data.get("add", [])}
        # With naive last-write-wins all but one would be lost; with
        # _locked_rewrite every writer should be preserved.
        assert added_terms == set(terms)


class TestOverrideOrder:
    """gpt-5.4 review #44 (rules.py): apply overrides AFTER add."""

    def test_override_reaches_added_term(self, tmp_path: Path):
        user_yaml = tmp_path / "user.yaml"
        user_yaml.write_text(
            "add:\n"
            "  - term: local-bad\n"
            "    suggest: 置換案\n"
            "    severity: ERROR\n"
            "overrides:\n"
            "  local-bad:\n"
            "    severity: INFO\n",
            encoding="utf-8",
        )
        from ja_output_harness.rules import load_rules
        cfg = load_rules(tune.BUNDLED_RULES_PATH, user_yaml)
        entry = next(e for e in cfg.banned if e.get("term") == "local-bad")
        assert entry["severity"] == "INFO"


class TestUserConfigPathResolution:
    """gpt-5.4 review #52: env vars are absolutized; new name takes priority."""

    def test_new_env_var_preferred(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("JA_OUTPUT_HARNESS_USER_CONFIG", str(tmp_path / "new.yaml"))
        monkeypatch.setenv("CODEX_JP_HARNESS_USER_CONFIG", str(tmp_path / "old.yaml"))
        from ja_output_harness.rules import resolve_user_config_path
        assert resolve_user_config_path() == (tmp_path / "new.yaml").resolve()

    def test_legacy_env_var_still_accepted(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("JA_OUTPUT_HARNESS_USER_CONFIG", raising=False)
        monkeypatch.setenv("CODEX_JP_HARNESS_USER_CONFIG", str(tmp_path / "legacy.yaml"))
        from ja_output_harness.rules import resolve_user_config_path
        assert resolve_user_config_path() == (tmp_path / "legacy.yaml").resolve()

    def test_relative_path_absolutized(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("JA_OUTPUT_HARNESS_USER_CONFIG", raising=False)
        monkeypatch.setenv("CODEX_JP_HARNESS_USER_CONFIG", "relative.yaml")
        from ja_output_harness.rules import resolve_user_config_path
        result = resolve_user_config_path()
        assert result.is_absolute()
        assert result == (tmp_path / "relative.yaml").resolve()


class TestDiscoverFileEncoding:
    """gpt-5.4 review #46: discover --file must survive non-UTF-8 bytes."""

    def test_utf8_file_parses(self, user_config: Path, tmp_path: Path, capsys):
        sample = tmp_path / "draft.txt"
        sample.write_text("context preview preview iframe iframe", encoding="utf-8")
        rc = tune.main(["discover", "--file", str(sample), "--min-occurrences", "1"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "preview" in out

    def test_cp932_file_falls_back(self, user_config: Path, tmp_path: Path, capsys):
        sample = tmp_path / "draft_cp932.txt"
        # Contains Japanese that is valid cp932 but invalid UTF-8.
        sample.write_bytes("対象を preview して review する。".encode("cp932"))
        rc = tune.main(["discover", "--file", str(sample), "--min-occurrences", "1"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "preview" in out

    def test_invalid_bytes_degrade_gracefully(self, user_config: Path, tmp_path: Path):
        # Byte sequence that is valid in neither UTF-8 nor cp932 (continuation
        # without lead byte). discover must not crash; replacement chars are
        # acceptable.
        sample = tmp_path / "bad.bin"
        sample.write_bytes(b"\xff\xfeabc preview preview\n")
        rc = tune.main(["discover", "--file", str(sample), "--min-occurrences", "1"])
        assert rc == 0


class TestShow:
    def test_show_prints_bundled_count(self, user_config: Path, capsys):
        rc = tune.main(["show"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "effective banned terms" in out
        # Spot-check: at least one well-known bundled term appears
        assert "slice" in out

    def test_show_reflects_disable(self, user_config: Path, capsys):
        tune.main(["disable", "slice"])
        tune.main(["show"])
        out = capsys.readouterr().out
        # `slice` line should be gone
        assert "- slice " not in out
