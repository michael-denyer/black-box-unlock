"""Tests for GitHub Actions adapters and raw-response parsing."""

import json
import subprocess
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from black_box_unlock.cicd.github_actions import (
    fetch_jobs_for_run,
    fetch_workflow_runs,
    get_files_changed,
    parse_workflow_runs,
)
from black_box_unlock.cicd.models import WorkflowJob, WorkflowRun


def _raw_run(**overrides) -> dict:
    payload = {
        "id": 123,
        "name": "CI",
        "head_sha": "abc123",
        "conclusion": "success",
        "created_at": "2026-01-26T10:00:00Z",
        "run_attempt": 1,
    }
    payload.update(overrides)
    return payload


class TestParseWorkflowRuns:
    def test_parses_rest_shape_into_typed_model(self):
        runs = parse_workflow_runs([_raw_run(run_attempt=2)])

        assert runs == [
            WorkflowRun(
                run_id=123,
                workflow_name="CI",
                commit_sha="abc123",
                conclusion="success",
                created_at=datetime(2026, 1, 26, 10, 0, tzinfo=timezone.utc),
                run_attempt=2,
            )
        ]

    def test_null_conclusion_is_unknown(self):
        run = parse_workflow_runs([_raw_run(conclusion=None)])[0]

        assert run.conclusion == "unknown"
        assert run.is_failure is False

    def test_empty_list_returns_empty(self):
        assert parse_workflow_runs([]) == []


class TestFetchWorkflowRuns:
    @patch("black_box_unlock.cicd.github_actions.subprocess.run")
    def test_uses_one_rest_endpoint_and_repo_cwd(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            stdout=json.dumps({"workflow_runs": [_raw_run()]}),
        )

        runs = fetch_workflow_runs(limit=25, repo_path=tmp_path)

        command = mock_run.call_args.args[0]
        assert command == [
            "gh",
            "api",
            "/repos/{owner}/{repo}/actions/runs?per_page=25",
        ]
        assert mock_run.call_args.kwargs["cwd"] == tmp_path
        assert runs[0].run_id == 123


class TestGetFilesChanged:
    @patch("black_box_unlock.cicd.github_actions.subprocess.run")
    def test_returns_nonempty_paths_and_uses_repo_cwd(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(stdout="src/main.py\n\ntests/test_main.py\n")

        files = get_files_changed("abc123", repo_path=tmp_path)

        assert files == ["src/main.py", "tests/test_main.py"]
        assert mock_run.call_args.kwargs["cwd"] == tmp_path
        assert mock_run.call_args.args[0] == [
            "git",
            "show",
            "--name-only",
            "--format=",
            "abc123",
        ]

    @patch("black_box_unlock.cicd.github_actions.subprocess.run")
    def test_invalid_sha_propagates_to_collector(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(128, ["git", "show"])

        with pytest.raises(subprocess.CalledProcessError):
            get_files_changed("invalid")


class TestFetchJobsForRun:
    @patch("black_box_unlock.cicd.github_actions.subprocess.run")
    def test_fetches_all_attempts_and_returns_typed_jobs(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            stdout=json.dumps(
                {
                    "jobs": [
                        {
                            "name": "test (3.11)",
                            "run_attempt": 2,
                            "steps": [
                                {
                                    "name": "Run tests",
                                    "conclusion": "success",
                                    "completed_at": "2026-06-02T10:00:00Z",
                                }
                            ],
                        }
                    ]
                }
            )
        )

        jobs = fetch_jobs_for_run(123, repo_path=tmp_path)

        assert jobs == [
            WorkflowJob(
                name="test (3.11)",
                run_attempt=2,
                steps=[
                    {
                        "name": "Run tests",
                        "conclusion": "success",
                        "completed_at": "2026-06-02T10:00:00Z",
                    }
                ],
            )
        ]
        endpoint = mock_run.call_args.args[0][-1]
        assert endpoint.endswith("/runs/123/jobs?filter=all&per_page=100")
        assert mock_run.call_args.kwargs["cwd"] == tmp_path
