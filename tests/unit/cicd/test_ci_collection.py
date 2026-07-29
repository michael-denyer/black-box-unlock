"""Behavior tests for the complete CI signal collection interface."""

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from black_box_unlock.cicd.github_actions import collect_ci_signals
from black_box_unlock.cicd.models import WorkflowRun
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
        mock_runs.return_value = [_run(1, run_attempt=2)]
        mock_files.return_value = ["src/a.py"]
        mock_jobs.return_value = []

        result = collect_ci_signals(tmp_path, limit=25)

        mock_runs.assert_called_once_with(limit=25, repo_path=tmp_path)
        mock_files.assert_called_once_with("sha-1", repo_path=tmp_path)
        mock_jobs.assert_called_once_with(1, repo_path=tmp_path)
        assert result.status.state is SignalState.available
        assert result.file_failures == {"src/a.py": 1}

    @patch("black_box_unlock.cicd.github_actions.get_files_changed")
    @patch("black_box_unlock.cicd.github_actions.fetch_workflow_runs")
    def test_one_bad_run_keeps_successful_attribution(self, mock_runs, mock_files, tmp_path):
        mock_runs.return_value = [_run(1), _run(2)]
        mock_files.side_effect = [
            ["src/a.py"],
            subprocess.CalledProcessError(128, ["git", "show"]),
        ]

        result = collect_ci_signals(tmp_path)

        assert result.status.state is SignalState.partial
        assert result.file_failures == {"src/a.py": 1}
        assert len(result.status.errors) == 1
        assert "run 2" in result.status.errors[0]

    @patch("black_box_unlock.cicd.github_actions.fetch_workflow_runs")
    def test_run_fetch_failure_is_explicitly_unavailable(self, mock_runs, tmp_path):
        mock_runs.side_effect = FileNotFoundError("gh not found")

        result = collect_ci_signals(tmp_path)

        assert result.status.state is SignalState.unavailable
        assert result.file_failures == {}
        assert result.flaky_steps == []
        assert result.status.errors == ["gh not found"]

    @patch("black_box_unlock.cicd.github_actions.fetch_workflow_runs")
    def test_empty_successful_snapshot_is_available(self, mock_runs, tmp_path):
        mock_runs.return_value = []

        result = collect_ci_signals(Path(tmp_path))

        assert result.status.state is SignalState.available
        assert result.status.errors == []
