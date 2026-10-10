"""Integration tests for split-history validation against scratch git repos.

Each scratch repo is built with explicit author and committer dates relative to
now, so the `--since` window and the cutoff land where the test says they do.
"""

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from black_box_unlock.validation import (
    MIN_TEST_BUGFIX_COMMITS,
    MIN_UNIVERSE_FILES,
    validate_repo,
)

INDENTED = "def f(x):\n    if x:\n        return 1\n    return 0\n"
FLAT = "X = 1\nY = 2\n"


def _days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


class ScratchRepo:
    """A real git repo whose commits carry caller-chosen author and committer dates."""

    def __init__(self, root: Path) -> None:
        self.path = root / "repo"
        self.path.mkdir()
        self._home = root
        self._git("init", "--initial-branch=main")

    def _git(self, *args: str, author_days: int = 0, committer_days: int = 0) -> None:
        subprocess.run(
            ["git", "-C", str(self.path), *args],
            check=True,
            capture_output=True,
            env={
                "GIT_AUTHOR_NAME": "Alice",
                "GIT_AUTHOR_EMAIL": "alice@example.com",
                "GIT_COMMITTER_NAME": "Alice",
                "GIT_COMMITTER_EMAIL": "alice@example.com",
                "GIT_AUTHOR_DATE": _days_ago(author_days),
                "GIT_COMMITTER_DATE": _days_ago(committer_days),
                "PATH": "/usr/bin:/bin",
                "HOME": str(self._home),
            },
        )

    def commit(
        self,
        message: str,
        files: dict[str, str | None],
        *,
        days_ago: int,
        author_days_ago: int | None = None,
    ) -> None:
        """Write (or delete, for None) each file and commit at the given committer age."""
        for name, content in files.items():
            target = self.path / name
            if content is None:
                target.unlink()
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
        self._git("add", "-A")
        self._git(
            "commit",
            "-m",
            message,
            author_days=days_ago if author_days_ago is None else author_days_ago,
            committer_days=days_ago,
        )

    def branch(self, name: str, start: str = "HEAD") -> None:
        self._git("switch", "-c", name, start)

    def switch(self, name: str) -> None:
        self._git("switch", name)

    def merge(self, branch: str, message: str, *, days_ago: int) -> None:
        """Merge `branch` with a merge commit (no fast-forward) at the given age."""
        self._git(
            "merge", "--no-ff", "-m", message, branch, author_days=days_ago, committer_days=days_ago
        )


@pytest.fixture
def scratch(tmp_path: Path) -> ScratchRepo:
    return ScratchRepo(tmp_path)


def _seed_train_half(repo: ScratchRepo) -> None:
    """Three train-half commits: hot.py churns three times, cold.py once."""
    repo.commit("feat: a", {"hot.py": INDENTED, "cold.py": FLAT}, days_ago=90)
    repo.commit("feat: b", {"hot.py": INDENTED + "Z = 3\n"}, days_ago=80)
    repo.commit("feat: c", {"hot.py": INDENTED + "Z = 4\n"}, days_ago=70)


class TestCutoffUniverse:
    def test_file_deleted_after_cutoff_stays_in_universe(self, scratch: ScratchRepo):
        _seed_train_half(scratch)
        scratch.commit("feat: add gone", {"gone.py": INDENTED}, days_ago=60)
        scratch.commit("chore: drop gone", {"gone.py": None}, days_ago=10)
        scratch.commit("fix: crash", {"hot.py": INDENTED + "Z = 5\n"}, days_ago=5)

        report = validate_repo(scratch.path, days=100, split=0.5)

        assert report.universe_size == 3  # hot.py, cold.py, gone.py (existed at the cutoff)

    def test_complexity_is_measured_from_the_cutoff_tree(self, scratch: ScratchRepo):
        # cold.py is flat at the cutoff and deeply indented afterwards. Read from
        # HEAD, cold.py (1 commit x 30 levels) outscores hot.py (3 commits x 3).
        # Read from the cutoff tree, hot.py ranks first.
        _seed_train_half(scratch)
        scratch.commit("feat: nest cold", {"cold.py": INDENTED * 10}, days_ago=10)
        scratch.commit("fix: crash", {"hot.py": INDENTED + "Z = 5\n"}, days_ago=5)

        report = validate_repo(scratch.path, days=100, split=0.5)

        assert report.methods["hotspot"].top_files == ["hot.py"]
        assert len(report.cutoff_sha) == 40

    def test_path_that_became_a_directory_is_skipped(self, scratch: ScratchRepo):
        # pkg was a file, then a package. At the cutoff "pkg" names a tree, which
        # has no lines to count, so only pkg/__init__.py is in the universe.
        scratch.commit("feat: pkg file", {"pkg": FLAT}, days_ago=90)
        scratch.commit("feat: pkg package", {"pkg": None, "pkg/__init__.py": INDENTED}, days_ago=80)
        scratch.commit("fix: crash", {"pkg/__init__.py": INDENTED + "Z = 5\n"}, days_ago=5)

        report = validate_repo(scratch.path, days=100, split=0.5)

        assert report.methods["churn"].top_files == ["pkg/__init__.py"]
        assert report.universe_size == 1


class TestAncestrySplit:
    def test_side_branch_commit_merged_after_the_cutoff_is_test_half(self, scratch: ScratchRepo):
        # The fix is committed before the cutoff date but is not an ancestor of
        # the cutoff commit, so the cutoff tree never saw it: it belongs to the
        # test half, and x.py is not in the universe.
        scratch.commit("init", {"a.py": INDENTED}, days_ago=300)
        scratch.branch("side")
        scratch.commit("fix: x crash", {"x.py": FLAT}, days_ago=250)
        scratch.switch("main")
        scratch.commit("tweak a", {"a.py": INDENTED + "Z = 1\n"}, days_ago=220)
        scratch.merge("side", "Merge branch 'side'", days_ago=100)

        report = validate_repo(scratch.path, days=400, split=0.5)

        assert report.train_commits == 2
        assert report.test_commits == 2
        assert report.test_bugfix_commits == 1
        assert report.methods["churn"].top_files == ["a.py"]
        assert report.universe_size == 1


class TestOneClock:
    def test_rebased_fix_lands_on_the_committer_date_side(self, scratch: ScratchRepo):
        # Authored before the cutoff, committed (rebased) after it. The committer
        # clock orders history, so the fix belongs to the test half.
        _seed_train_half(scratch)
        scratch.commit(
            "fix: crash", {"hot.py": INDENTED + "Z = 5\n"}, days_ago=10, author_days_ago=85
        )

        report = validate_repo(scratch.path, days=100, split=0.5)

        assert report.clock == "committer"
        assert report.test_bugfix_commits == 1
        assert report.methods["hotspot"].top_decile_share == pytest.approx(1.0)


class TestBaselines:
    def _seed(self, repo: ScratchRepo) -> None:
        # flat.py churns most but has no indentation; long.py is the longest file.
        # Hotspot, churn, and length rankings therefore each pick a different file.
        _seed_train_half(repo)
        for i in range(4):
            repo.commit(f"feat: flat {i}", {"flat.py": FLAT + f"N = {i}\n"}, days_ago=88 - i)
        repo.commit("feat: long", {"long.py": "X = 1\n" * 200}, days_ago=75)
        repo.commit("fix: crash", {"hot.py": INDENTED + "Z = 5\n"}, days_ago=10)
        repo.commit("fix: flat", {"flat.py": FLAT}, days_ago=8)

    def test_churn_and_length_rankings_sit_beside_hotspot(self, scratch: ScratchRepo):
        self._seed(scratch)

        report = validate_repo(scratch.path, days=100, split=0.5)

        assert report.methods["hotspot"].top_files == ["hot.py"]
        assert report.methods["churn"].top_files == ["flat.py"]
        assert report.methods["length"].top_files == ["long.py"]
        assert report.methods["churn"].top_decile_share == pytest.approx(0.5)

    def test_random_baseline_is_seeded_and_reproducible(self, scratch: ScratchRepo):
        self._seed(scratch)

        first = validate_repo(scratch.path, days=100, split=0.5).random
        second = validate_repo(scratch.path, days=100, split=0.5).random

        assert first.draws == 200
        assert first == second
        # four files, one top slot, two touches split over two files: each draw
        # scores 0.5 or 0, so the mean sits strictly between and the sd is positive
        assert 0 < first.top_decile_share_mean < 0.5
        assert first.top_decile_share_sd > 0


class TestSignificance:
    def test_tiny_repo_is_flagged_insufficient_with_counts(self, scratch: ScratchRepo):
        _seed_train_half(scratch)
        scratch.commit("fix: crash", {"hot.py": INDENTED + "Z = 5\n"}, days_ago=10)

        report = validate_repo(scratch.path, days=100, split=0.5)

        assert report.insufficient_data is True
        assert report.insufficient_reasons == [
            f"2 universe files < {MIN_UNIVERSE_FILES}",
            f"1 post-cutoff bug-fix commits < {MIN_TEST_BUGFIX_COMMITS}",
        ]

    def test_fix_named_merge_commit_is_not_a_bugfix_commit(self, scratch: ScratchRepo):
        # A GitHub merge subject carries the branch name, so it matches the
        # bug-fix pattern, but it changes no files and its fix is already counted.
        _seed_train_half(scratch)
        scratch.branch("fix/crash")
        scratch.commit("fix: crash", {"hot.py": INDENTED + "Z = 5\n"}, days_ago=10)
        scratch.switch("main")
        scratch.merge("fix/crash", "Merge pull request #1 from me/fix/crash", days_ago=5)

        report = validate_repo(scratch.path, days=100, split=0.5)

        assert report.test_commits == 2
        assert report.test_bugfix_commits == 1

    def test_p_value_compares_hotspot_share_with_random_draws(self, scratch: ScratchRepo):
        # hot.py takes the only touch. One random draw in four puts hot.py on
        # top, so about a quarter of 200 draws tie the hotspot share of 1.0.
        _seed_train_half(scratch)
        scratch.commit("feat: more", {"flat.py": FLAT, "long.py": "X = 1\n" * 50}, days_ago=75)
        scratch.commit("fix: crash", {"hot.py": INDENTED + "Z = 5\n"}, days_ago=10)

        report = validate_repo(scratch.path, days=100, split=0.5)

        assert report.methods["hotspot"].top_decile_share == pytest.approx(1.0)
        assert 0.15 < report.p_value < 0.35
