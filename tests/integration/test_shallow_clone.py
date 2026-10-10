"""Shallow clones report truncated history in provenance and on stderr."""

import os
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from black_box_unlock.analysis import SHALLOW_CLONE_WARNING, build_provenance
from black_box_unlock.cli import app

runner = CliRunner()


def _git(*args: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Alice",
        "GIT_AUTHOR_EMAIL": "alice@example.com",
        "GIT_COMMITTER_NAME": "Alice",
        "GIT_COMMITTER_EMAIL": "alice@example.com",
    }
    subprocess.run(["git", *args], check=True, capture_output=True, env=env)


@pytest.fixture
def source_repo(tmp_path: Path) -> Path:
    """A repository with two commits, cloned from a file:// URL so --depth applies."""
    repo = tmp_path / "source"
    repo.mkdir()
    _git("-C", str(repo), "init")
    (repo / "main.py").write_text("print('hello')\n")
    _git("-C", str(repo), "add", "main.py")
    _git("-C", str(repo), "commit", "-m", "feat: initial")
    (repo / "main.py").write_text("print('hello')\nprint('world')\n")
    _git("-C", str(repo), "commit", "-am", "fix: add world")
    return repo


@pytest.fixture
def shallow_clone(source_repo: Path, tmp_path: Path) -> Path:
    target = tmp_path / "shallow"
    _git("clone", "--depth", "1", f"file://{source_repo}", str(target))
    return target


@pytest.fixture
def full_clone(source_repo: Path, tmp_path: Path) -> Path:
    target = tmp_path / "full"
    _git("clone", f"file://{source_repo}", str(target))
    return target


def test_shallow_clone_provenance_carries_the_truncation_warning(shallow_clone):
    provenance = build_provenance(shallow_clone, 30, False, oid=None)

    assert provenance.shallow_clone is True
    assert provenance.warnings == [SHALLOW_CLONE_WARNING]


def test_full_clone_provenance_has_no_warning(full_clone):
    provenance = build_provenance(full_clone, 30, False, oid=None)

    assert provenance.shallow_clone is False
    assert provenance.warnings == []


def test_analyze_repo_prints_the_warning_for_a_shallow_clone(shallow_clone):
    result = runner.invoke(app, ["analyze-repo", "--repo", str(shallow_clone), "--no-ci"])

    assert result.exit_code == 0, result.stderr
    assert SHALLOW_CLONE_WARNING in result.stderr


def test_analyze_repo_is_silent_for_a_full_clone(full_clone):
    result = runner.invoke(app, ["analyze-repo", "--repo", str(full_clone), "--no-ci"])

    assert result.exit_code == 0, result.stderr
    assert SHALLOW_CLONE_WARNING not in result.stderr


def test_review_change_prints_the_warning_for_a_shallow_clone(shallow_clone):
    result = runner.invoke(app, ["review-change", "--repo", str(shallow_clone)])

    assert result.exit_code == 0, result.stderr
    assert SHALLOW_CLONE_WARNING in result.stderr


def test_review_change_is_silent_for_a_full_clone(full_clone):
    result = runner.invoke(app, ["review-change", "--repo", str(full_clone)])

    assert result.exit_code == 0, result.stderr
    assert SHALLOW_CLONE_WARNING not in result.stderr
