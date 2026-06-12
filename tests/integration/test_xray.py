"""Integration tests for xray_file against a real synthetic repository."""

import subprocess

import pytest

from black_box_unlock.core.exceptions import NotAGitRepoError
from black_box_unlock.git.xray import xray_file

ALPHA_V1 = "def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n"
ALPHA_V2 = "def alpha():\n    x = 1\n    return x\n\n\ndef beta():\n    return 2\n"
ALPHA_V3 = "def alpha():\n    x = 2\n    return x\n\n\ndef beta():\n    return 2\n"
BETA_V2 = "def alpha():\n    x = 2\n    return x\n\n\ndef beta():\n    y = 5\n    return y\n"


def _run(args: list[str], cwd) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def xray_repo(tmp_path):
    _run(["git", "init", "-b", "main"], tmp_path)
    _run(["git", "config", "user.email", "t@example.com"], tmp_path)
    _run(["git", "config", "user.name", "Tester"], tmp_path)
    mod = tmp_path / "mod.py"
    for i, content in enumerate([ALPHA_V1, ALPHA_V2, ALPHA_V3, BETA_V2]):
        mod.write_text(content)
        _run(["git", "add", "."], tmp_path)
        _run(["git", "commit", "-m", f"step {i}"], tmp_path)
    return tmp_path


class TestXrayFile:
    def test_per_function_revision_counts(self, xray_repo):
        result = xray_file(xray_repo, "mod.py", days=365)
        by_name = {f.name: f for f in result.functions}
        assert by_name["alpha"].revisions == 3  # creation + two edits
        assert by_name["beta"].revisions == 2  # creation + one edit

    def test_complexity_and_score_from_current_snapshot(self, xray_repo):
        result = xray_file(xray_repo, "mod.py", days=365)
        alpha = next(f for f in result.functions if f.name == "alpha")
        assert alpha.complexity == 2.0  # two indented lines in final alpha
        assert alpha.hotspot_score == 6.0
        assert alpha.start_line == 1 and alpha.end_line == 3

    def test_sorted_by_score_descending(self, xray_repo):
        result = xray_file(xray_repo, "mod.py", days=365)
        scores = [f.hotspot_score for f in result.functions]
        assert scores == sorted(scores, reverse=True)

    def test_revision_cap(self, xray_repo):
        result = xray_file(xray_repo, "mod.py", days=365, rev_cap=2)
        assert result.revisions_analyzed == 2
        assert result.revision_cap_hit is True

    def test_no_history_returns_empty(self, xray_repo):
        result = xray_file(xray_repo, "missing.py", days=365)
        assert result.functions == [] and result.revisions_analyzed == 0

    def test_not_a_repo_raises(self, tmp_path):
        with pytest.raises(NotAGitRepoError):
            xray_file(tmp_path / "nowhere", "mod.py")

    def test_vanished_function_excluded(self, xray_repo):
        mod = xray_repo / "mod.py"
        mod.write_text("def alpha():\n    x = 2\n    return x\n")  # beta deleted
        _run(["git", "add", "."], xray_repo)
        _run(["git", "commit", "-m", "drop beta"], xray_repo)
        result = xray_file(xray_repo, "mod.py", days=365)
        assert "beta" not in {f.name for f in result.functions}
