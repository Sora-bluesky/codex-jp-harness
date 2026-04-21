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
