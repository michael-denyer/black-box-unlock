"""Integration tests for git churn extraction against a real repository."""

import subprocess
from pathlib import Path

import pytest

from black_box_unlock.git.churn import extract_file_churn


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Path:
    """Build a real git repo with two commits touching two files."""
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            env={
                "GIT_AUTHOR_NAME": "Alice",
                "GIT_AUTHOR_EMAIL": "alice@example.com",
                "GIT_COMMITTER_NAME": "Alice",
                "GIT_COMMITTER_EMAIL": "alice@example.com",
                "PATH": "/usr/bin:/bin",
                "HOME": str(tmp_path),
            },
        )

    git("init")
    (repo / "main.py").write_text("print('hello')\n")
    git("add", "main.py")
    git("commit", "-m", "feat: initial")
    (repo / "main.py").write_text("print('hello')\nprint('world')\n")
    (repo / "util.py").write_text("x = 1\n")
    git("add", "main.py", "util.py")
    git("commit", "-m", "fix: add world and util")
    return repo


class TestExtractFileChurnIntegration:
    def test_extracts_churn_from_fixture_repo(self, fixture_repo):
        result = extract_file_churn(fixture_repo, since_days=30)

        by_path = {c.path: c for c in result}
        assert set(by_path) == {"main.py", "util.py"}
        assert by_path["main.py"].commits == 2
        assert by_path["util.py"].commits == 1
        # 1 line in initial commit + 1 appended line in second commit
        assert by_path["main.py"].lines_added == 2

    def test_results_sortable_by_churn(self, fixture_repo):
        result = extract_file_churn(fixture_repo, since_days=30)

        ranked = sorted(result, key=lambda c: c.total_lines_changed, reverse=True)
        assert ranked[0].path == "main.py"
