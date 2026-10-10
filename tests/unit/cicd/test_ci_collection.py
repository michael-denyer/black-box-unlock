"""Behavior tests for the complete CI signal collection interface."""

import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from black_box_unlock.cicd.github_actions import collect_ci_signals
from black_box_unlock.cicd.models import WorkflowJob, WorkflowRun
from black_box_unlock.core.models import SignalState


def _run(
    run_id: int,
    *,
    conclusion: str = "failure",
    run_attempt: int = 1,
) -> WorkflowRun:
    return WorkflowRun(
        run_id=run_id,
        workflow_name="CI",
        run_url=f"https://github.com/example/repo/actions/runs/{run_id}",
        commit_sha=f"sha-{run_id}",
        conclusion=conclusion,
        created_at=datetime(2026, 6, run_id, tzinfo=timezone.utc),
        run_attempt=run_attempt,
    )


class TestCollectCISignals:
    @patch("black_box_unlock.cicd.github_actions.fetch_jobs_for_run")
    @patch("black_box_unlock.cicd.github_actions.get_files_changed")
    @patch("black_box_unlock.cicd.github_actions.fetch_workflow_runs")
    def test_one_run_snapshot_feeds_both_signals(
        self,
        mock_runs,
        mock_files,
        mock_jobs,
        tmp_path,
    ):
        mock_runs.return_value = ([_run(1, run_attempt=2)], False)
        mock_files.return_value = ["src/a.py"]
        mock_jobs.return_value = []

        result = collect_ci_signals(tmp_path, limit=25)

        mock_runs.assert_called_once_with(limit=25, repo_path=tmp_path, since=None)
        mock_files.assert_called_once_with("sha-1", repo_path=tmp_path)
        mock_jobs.assert_called_once_with(1, repo_path=tmp_path)
        assert result.status.state is SignalState.available
        assert result.file_failures == {"src/a.py": 1}
        assert result.failed_runs[0].run_url.endswith("/1")
        assert result.failed_runs[0].implicated_paths == ["src/a.py"]

    @patch("black_box_unlock.cicd.github_actions.get_files_changed")
    @patch("black_box_unlock.cicd.github_actions.fetch_workflow_runs")
    def test_one_bad_run_keeps_successful_attribution(self, mock_runs, mock_files, tmp_path):
        mock_runs.return_value = ([_run(1), _run(2)], False)
        mock_files.side_effect = [
            ["src/a.py"],
            subprocess.CalledProcessError(128, ["git", "show"]),
        ]

        result = collect_ci_signals(tmp_path)

        assert result.status.state is SignalState.partial
        assert result.file_failures == {"src/a.py": 1}
        assert len(result.status.errors) == 1
        assert "run 2" in result.status.errors[0]
        assert [run.implicated_paths for run in result.failed_runs] == [
            ["src/a.py"],
            [],
        ]

    @patch("black_box_unlock.cicd.github_actions.fetch_workflow_runs")
    def test_run_fetch_failure_is_explicitly_unavailable(self, mock_runs, tmp_path):
        mock_runs.side_effect = FileNotFoundError("gh not found")

        result = collect_ci_signals(tmp_path)

        assert result.status.state is SignalState.unavailable
        assert result.file_failures == {}
        assert result.failed_runs == []
        assert result.flaky_steps == []
        assert result.status.errors == ["gh not found"]

    @patch("black_box_unlock.cicd.github_actions.fetch_workflow_runs")
    def test_days_bounds_the_run_window(self, mock_runs, tmp_path):
        mock_runs.return_value = ([], False)
        before = datetime.now(timezone.utc)

        collect_ci_signals(tmp_path, days=30)

        since = mock_runs.call_args.kwargs["since"]
        assert (
            before - timedelta(days=30) <= since <= datetime.now(timezone.utc) - timedelta(days=30)
        )

    @patch("black_box_unlock.cicd.github_actions.subprocess.run")
    def test_gh_timeout_on_the_run_fetch_is_unavailable_with_the_reason(self, mock_gh, tmp_path):
        mock_gh.side_effect = subprocess.TimeoutExpired(["gh", "api"], 60)

        result = collect_ci_signals(tmp_path)

        assert result.status.state is SignalState.unavailable
        assert "timed out after 60" in result.status.errors[0]

    @patch("black_box_unlock.cicd.github_actions.fetch_jobs_for_run")
    @patch("black_box_unlock.cicd.github_actions.fetch_workflow_runs")
    def test_gh_timeout_on_one_jobs_fetch_is_partial(self, mock_runs, mock_jobs, tmp_path):
        mock_runs.return_value = ([_run(1, conclusion="success", run_attempt=2)], False)
        mock_jobs.side_effect = subprocess.TimeoutExpired(["gh", "api"], 60)

        result = collect_ci_signals(tmp_path)

        assert result.status.state is SignalState.partial
        assert "jobs for run 1" in result.status.errors[0]
        assert "timed out" in result.status.errors[0]

    @patch("black_box_unlock.cicd.github_actions.fetch_jobs_for_run")
    @patch("black_box_unlock.cicd.github_actions.fetch_workflow_runs")
    def test_failure_on_one_commit_then_pass_on_another_is_not_flaky(
        self, mock_runs, mock_jobs, tmp_path
    ):
        failing_commit = _run(1, conclusion="failure", run_attempt=2)
        fixed_commit = _run(2, conclusion="success", run_attempt=2)
        mock_runs.return_value = ([failing_commit, fixed_commit], False)
        mock_jobs.side_effect = lambda run_id, repo_path: [
            WorkflowJob.model_validate(
                {
                    "name": "test",
                    "run_attempt": 1 if run_id == 1 else 2,
                    "steps": [
                        {
                            "name": "Run tests",
                            "conclusion": "failure" if run_id == 1 else "success",
                            "completed_at": "2026-06-02T10:00:00Z",
                        }
                    ],
                }
            )
        ]

        with patch("black_box_unlock.cicd.github_actions.get_files_changed", return_value=[]):
            result = collect_ci_signals(tmp_path)

        assert result.flaky_steps == []

    @patch("black_box_unlock.cicd.github_actions.fetch_workflow_runs")
    def test_empty_successful_snapshot_is_available(self, mock_runs, tmp_path):
        mock_runs.return_value = ([], False)

        result = collect_ci_signals(Path(tmp_path))

        assert result.status.state is SignalState.available
        assert result.status.errors == []


class TestCIAttributionGitFailure:
    @patch("black_box_unlock.cicd.github_actions.fetch_workflow_runs")
    def test_git_stderr_reaches_the_warning_log_and_paths_stay_empty(self, mock_runs, tmp_path):
        from loguru import logger

        from black_box_unlock.analysis import run_analysis

        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        mock_runs.return_value = ([_run(1)], False)
        messages: list[str] = []
        sink = logger.add(messages.append, level="WARNING")
        try:
            result = run_analysis(tmp_path, include_ci=True, xray_top=0)
        finally:
            logger.remove(sink)

        assert result.failed_ci_runs[0].implicated_paths == []
        assert result.ci_status.state is SignalState.partial
        assert any("unknown revision" in message for message in messages)
        assert "unknown revision" in result.ci_status.errors[0]


class TestGetFilesChangedPaths:
    def test_non_ascii_paths_are_returned_unquoted(self, tmp_path):
        from black_box_unlock.cicd.github_actions import get_files_changed

        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        (tmp_path / "café.py").write_text("x = 1\n")
        env = {
            "GIT_AUTHOR_NAME": "a",
            "GIT_AUTHOR_EMAIL": "a@x",
            "GIT_COMMITTER_NAME": "a",
            "GIT_COMMITTER_EMAIL": "a@x",
            "HOME": str(tmp_path),
        }
        subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "add"],
            check=True,
            capture_output=True,
            env=env,
        )

        assert get_files_changed("HEAD", tmp_path) == ["café.py"]


_GIT_ENV = {
    "GIT_AUTHOR_NAME": "a",
    "GIT_AUTHOR_EMAIL": "a@x",
    "GIT_COMMITTER_NAME": "a",
    "GIT_COMMITTER_EMAIL": "a@x",
}


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **_GIT_ENV},
    )
    return result.stdout.strip()


class TestGetFilesChangedMergeCommit:
    def test_merge_commit_lists_the_files_it_brought_in(self, tmp_path):
        from black_box_unlock.cicd.github_actions import get_files_changed

        _git(tmp_path, "init", "-b", "main")
        _git(tmp_path, "commit", "--allow-empty", "-m", "base")
        _git(tmp_path, "checkout", "-b", "feature")
        (tmp_path / "feature.py").write_text("x = 1\n")
        _git(tmp_path, "add", ".")
        _git(tmp_path, "commit", "-m", "feature")
        _git(tmp_path, "checkout", "main")
        (tmp_path / "mainline.py").write_text("y = 2\n")
        _git(tmp_path, "add", ".")
        _git(tmp_path, "commit", "-m", "mainline")
        _git(tmp_path, "merge", "--no-ff", "feature", "-m", "merge feature")
        merge_sha = _git(tmp_path, "rev-parse", "HEAD")

        assert get_files_changed(merge_sha, tmp_path) == ["feature.py"]


class TestRunSnapshotTruncation:
    @patch("black_box_unlock.cicd.github_actions.fetch_jobs_for_run")
    @patch("black_box_unlock.cicd.github_actions.get_files_changed")
    @patch("black_box_unlock.cicd.github_actions.fetch_workflow_runs")
    def test_a_full_last_page_marks_the_result_partial(self, mock_runs, mock_files, mock_jobs):
        mock_runs.return_value = ([_run(1)], True)
        mock_files.return_value = []
        mock_jobs.return_value = []

        analysis = collect_ci_signals(repo_path=Path("."))

        assert analysis.status.state == SignalState.partial
        assert any("truncated" in error for error in analysis.status.errors)
