"""Tests for the ja-output-toggle CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from ja_output_harness import toggle


@pytest.fixture
def codex_home(monkeypatch, tmp_path: Path) -> Path:
    home = tmp_path / ".codex"
    monkeypatch.setenv("CODEX_HOME", str(home))
    return home


def _mode(codex_home: Path) -> str:
    path = codex_home / "state" / "jp-harness-mode"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _bak(codex_home: Path) -> str:
    path = codex_home / "state" / "jp-harness-mode.bak"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


class TestStatus:
    def test_unset_prints_default(self, codex_home, capsys):
        rc = toggle.main(["status"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "unset" in out

    def test_shows_current_mode(self, codex_home, capsys):
        (codex_home / "state").mkdir(parents=True)
        (codex_home / "state" / "jp-harness-mode").write_text("strict-lite\n")
        rc = toggle.main(["status"])
        assert rc == 0
        assert "strict-lite" in capsys.readouterr().out


class TestOff:
    def test_off_from_strict_lite_saves_bak(self, codex_home, capsys):
        (codex_home / "state").mkdir(parents=True)
        (codex_home / "state" / "jp-harness-mode").write_text("strict-lite\n")
        rc = toggle.main(["off"])
        assert rc == 0
        assert _mode(codex_home) == "off"
        assert _bak(codex_home) == "strict-lite"

    def test_off_when_already_off_is_idempotent(self, codex_home, capsys):
        (codex_home / "state").mkdir(parents=True)
        (codex_home / "state" / "jp-harness-mode").write_text("off\n")
        rc = toggle.main(["off"])
        assert rc == 0
        assert _mode(codex_home) == "off"
        assert "already off" in capsys.readouterr().out

    def test_off_with_no_prior_mode_still_writes_off(self, codex_home, capsys):
        rc = toggle.main(["off"])
        assert rc == 0
        assert _mode(codex_home) == "off"


class TestOn:
    def test_on_restores_from_bak(self, codex_home, capsys):
        (codex_home / "state").mkdir(parents=True)
        (codex_home / "state" / "jp-harness-mode").write_text("off\n")
        (codex_home / "state" / "jp-harness-mode.bak").write_text("lite\n")
        rc = toggle.main(["on"])
        assert rc == 0
        assert _mode(codex_home) == "lite"

    def test_on_without_bak_uses_default(self, codex_home, capsys):
        (codex_home / "state").mkdir(parents=True)
        (codex_home / "state" / "jp-harness-mode").write_text("off\n")
        rc = toggle.main(["on"])
        assert rc == 0
        assert _mode(codex_home) == "strict-lite"

    def test_on_when_already_on_is_idempotent(self, codex_home, capsys):
        (codex_home / "state").mkdir(parents=True)
        (codex_home / "state" / "jp-harness-mode").write_text("strict-lite\n")
        rc = toggle.main(["on"])
        assert rc == 0
        assert _mode(codex_home) == "strict-lite"
        assert "already on" in capsys.readouterr().out


class TestSet:
    def test_set_valid_mode(self, codex_home, capsys):
        rc = toggle.main(["set", "lite"])
        assert rc == 0
        assert _mode(codex_home) == "lite"

    def test_set_invalid_mode_errors(self, codex_home, capsys):
        # argparse rejects via SystemExit(2) because `mode` is a choices arg.
        with pytest.raises(SystemExit) as exc:
            toggle.main(["set", "bogus"])
        assert exc.value.code == 2

    def test_set_saves_prior_to_bak(self, codex_home):
        (codex_home / "state").mkdir(parents=True)
        (codex_home / "state" / "jp-harness-mode").write_text("strict-lite\n")
        rc = toggle.main(["set", "lite"])
        assert rc == 0
        assert _mode(codex_home) == "lite"
        assert _bak(codex_home) == "strict-lite"


class TestRoundTrip:
    def test_off_on_cycle_restores(self, codex_home):
        (codex_home / "state").mkdir(parents=True)
        (codex_home / "state" / "jp-harness-mode").write_text("strict-lite\n")
        assert toggle.main(["off"]) == 0
        assert _mode(codex_home) == "off"
        assert toggle.main(["on"]) == 0
        assert _mode(codex_home) == "strict-lite"
