"""Guard against drift between runtime __version__ and packaging metadata.

Introduced after gpt-5.4 review caught __version__ stuck at 0.2.22 while
pyproject.toml advertised 0.3.0. CI now fails if the two diverge.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import ja_output_harness

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_runtime_version_matches_pyproject():
    with (REPO_ROOT / "pyproject.toml").open("rb") as f:
        meta = tomllib.load(f)
    assert ja_output_harness.__version__ == meta["project"]["version"]


def test_changelog_has_current_version_entry():
    current = ja_output_harness.__version__
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{current}]" in changelog, (
        f"CHANGELOG.md is missing an entry for v{current}"
    )


def test_installed_package_version_matches_runtime():
    """gpt-5.4 follow-up review: guard the packaged wheel, not just the tree.

    `importlib.metadata.version` reads the installed distribution metadata.
    When ``uv sync`` installed us in editable mode this mirrors pyproject;
    when a release wheel is installed via pip it reads the wheel's
    ``METADATA`` file. Either way, a mismatch between runtime __version__
    and the distribution metadata leaks straight into issue reports.
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        installed = version("ja-output-harness")
    except PackageNotFoundError:
        import pytest

        pytest.skip("ja-output-harness is not installed as a distribution")
    assert installed == ja_output_harness.__version__
