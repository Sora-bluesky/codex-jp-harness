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


SAMPLE_AGENTS = """# AGENTS.md

User-local rules here.

<!-- BEGIN ja-output-harness managed block -->
## 日本語技術文の品質ゲート (ja-output-harness lite)

Lorem ipsum managed content that should be evicted.
<!-- END ja-output-harness managed block -->

trailing user content kept unchanged.
"""


class TestFullFlag:
    def test_off_full_evicts_agents_block(self, codex_home):
        (codex_home).mkdir(parents=True, exist_ok=True)
        (codex_home / "AGENTS.md").write_text(SAMPLE_AGENTS, encoding="utf-8")
        rc = toggle.main(["off", "--full"])
        assert rc == 0
        agents_text = (codex_home / "AGENTS.md").read_text(encoding="utf-8")
        assert "BEGIN ja-output-harness" not in agents_text
        assert "User-local rules here." in agents_text
        assert "trailing user content kept unchanged." in agents_text
        bak = (codex_home / "AGENTS.md.bak-toggle").read_text(encoding="utf-8")
        assert "BEGIN ja-output-harness" in bak
        assert "END ja-output-harness" in bak

    def test_on_full_restores_agents_block(self, codex_home):
        (codex_home).mkdir(parents=True, exist_ok=True)
        (codex_home / "AGENTS.md").write_text(SAMPLE_AGENTS, encoding="utf-8")
        (codex_home / "state").mkdir(parents=True)
        (codex_home / "state" / "jp-harness-mode").write_text("strict-lite\n")
        assert toggle.main(["off", "--full"]) == 0
        assert toggle.main(["on", "--full"]) == 0
        agents_text = (codex_home / "AGENTS.md").read_text(encoding="utf-8")
        assert "BEGIN ja-output-harness" in agents_text
        assert "END ja-output-harness" in agents_text
        assert "User-local rules here." in agents_text
        assert "trailing user content kept unchanged." in agents_text
        assert not (codex_home / "AGENTS.md.bak-toggle").exists()

    def test_off_full_twice_is_idempotent(self, codex_home):
        (codex_home).mkdir(parents=True, exist_ok=True)
        (codex_home / "AGENTS.md").write_text(SAMPLE_AGENTS, encoding="utf-8")
        assert toggle.main(["off", "--full"]) == 0
        first = (codex_home / "AGENTS.md.bak-toggle").read_text(encoding="utf-8")
        # second run must not overwrite the bak (already-evicted message)
        assert toggle.main(["off", "--full"]) == 0
        second = (codex_home / "AGENTS.md.bak-toggle").read_text(encoding="utf-8")
        assert first == second

    def test_off_full_removes_reinserted_block_without_overwriting_bak(
        self, codex_home
    ):
        """Regression: if the installer re-runs between toggles, AGENTS.md can
        regain the managed block while .bak-toggle still sits on disk. The
        second ``off --full`` must evict the block again but preserve the
        original backup.
        """
        (codex_home).mkdir(parents=True, exist_ok=True)
        (codex_home / "AGENTS.md").write_text(SAMPLE_AGENTS, encoding="utf-8")
        assert toggle.main(["off", "--full"]) == 0
        bak_before = (codex_home / "AGENTS.md.bak-toggle").read_text(encoding="utf-8")
        # Simulate installer re-insertion with a different body.
        reinserted = (
            "# AGENTS.md\n\n"
            "User-local rules here.\n\n"
            "<!-- BEGIN ja-output-harness managed block -->\n"
            "## 日本語技術文の品質ゲート (NEW BODY)\n"
            "<!-- END ja-output-harness managed block -->\n"
        )
        (codex_home / "AGENTS.md").write_text(reinserted, encoding="utf-8")
        assert toggle.main(["off", "--full"]) == 0
        # Block must be gone from AGENTS.md now.
        agents_text = (codex_home / "AGENTS.md").read_text(encoding="utf-8")
        assert "BEGIN ja-output-harness" not in agents_text
        # Original backup must not be overwritten.
        bak_after = (codex_home / "AGENTS.md.bak-toggle").read_text(encoding="utf-8")
        assert bak_after == bak_before
        assert "NEW BODY" not in bak_after

    def test_off_full_without_managed_block_is_noop(self, codex_home, capsys):
        (codex_home).mkdir(parents=True, exist_ok=True)
        (codex_home / "AGENTS.md").write_text("just user content\n", encoding="utf-8")
        rc = toggle.main(["off", "--full"])
        assert rc == 0
        assert not (codex_home / "AGENTS.md.bak-toggle").exists()
        assert "no managed block" in capsys.readouterr().out

    def test_on_full_without_bak_warns(self, codex_home, capsys):
        (codex_home).mkdir(parents=True, exist_ok=True)
        (codex_home / "state").mkdir(parents=True)
        (codex_home / "state" / "jp-harness-mode").write_text("off\n")
        rc = toggle.main(["on", "--full"])
        assert rc == 0
        assert "no .bak-toggle to restore" in capsys.readouterr().out

    def test_status_reports_block_presence(self, codex_home, capsys):
        (codex_home).mkdir(parents=True, exist_ok=True)
        (codex_home / "AGENTS.md").write_text(SAMPLE_AGENTS, encoding="utf-8")
        rc = toggle.main(["status"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "AGENTS.md managed block: present" in out

    def test_status_reports_block_absent_after_full_off(self, codex_home, capsys):
        (codex_home).mkdir(parents=True, exist_ok=True)
        (codex_home / "AGENTS.md").write_text(SAMPLE_AGENTS, encoding="utf-8")
        toggle.main(["off", "--full"])
        capsys.readouterr()
        rc = toggle.main(["status"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "AGENTS.md managed block: absent" in out
        assert ".bak-toggle: exists" in out
