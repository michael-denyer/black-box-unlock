"""Tests for GitHub Actions adapters and raw-response parsing."""

import json
import subprocess
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from black_box_unlock.cicd.github_actions import (
    GH_TIMEOUT_SECONDS,
    MAX_PAGES,
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
        "html_url": "https://github.com/example/repo/actions/runs/123",
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
                run_url="https://github.com/example/repo/actions/runs/123",
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

        runs, _ = fetch_workflow_runs(limit=25, repo_path=tmp_path)

        command = mock_run.call_args.args[0]
        assert command == [
            "gh",
            "api",
            "/repos/{owner}/{repo}/actions/runs?per_page=25&page=1",
        ]
        assert mock_run.call_args.kwargs["cwd"] == tmp_path
        assert runs[0].run_id == 123

    @patch("black_box_unlock.cicd.github_actions.subprocess.run")
    def test_every_gh_call_has_a_timeout(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(stdout=json.dumps({"workflow_runs": []}))

        fetch_workflow_runs(repo_path=tmp_path)

        assert mock_run.call_args.kwargs["timeout"] == GH_TIMEOUT_SECONDS

    @patch("black_box_unlock.cicd.github_actions.subprocess.run")
    def test_follows_pages_until_a_short_page(self, mock_run, tmp_path):
        page1 = [_raw_run(id=1), _raw_run(id=2)]
        page2 = [_raw_run(id=3)]
        mock_run.side_effect = [
            MagicMock(stdout=json.dumps({"workflow_runs": page1})),
            MagicMock(stdout=json.dumps({"workflow_runs": page2})),
        ]

        runs, truncated = fetch_workflow_runs(limit=2, repo_path=tmp_path)

        assert [run.run_id for run in runs] == [1, 2, 3]
        assert truncated is False
        endpoints = [call.args[0][-1] for call in mock_run.call_args_list]
        assert endpoints == [
            "/repos/{owner}/{repo}/actions/runs?per_page=2&page=1",
            "/repos/{owner}/{repo}/actions/runs?per_page=2&page=2",
        ]

    @patch("black_box_unlock.cicd.github_actions.subprocess.run")
    def test_runs_repeated_across_pages_are_kept_once(self, mock_run, tmp_path):
        mock_run.side_effect = [
            MagicMock(stdout=json.dumps({"workflow_runs": [_raw_run(id=1), _raw_run(id=2)]})),
            MagicMock(stdout=json.dumps({"workflow_runs": [_raw_run(id=2)]})),
        ]

        runs, _ = fetch_workflow_runs(limit=2, repo_path=tmp_path)

        assert [run.run_id for run in runs] == [1, 2]

    @patch("black_box_unlock.cicd.github_actions.subprocess.run")
    def test_page_following_is_bounded(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            stdout=json.dumps({"workflow_runs": [_raw_run(), _raw_run(id=2)]})
        )

        _, truncated = fetch_workflow_runs(limit=2, repo_path=tmp_path)

        assert mock_run.call_count == MAX_PAGES
        assert truncated is True

    @patch("black_box_unlock.cicd.github_actions.subprocess.run")
    def test_since_filters_runs_created_before_the_window(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            stdout=json.dumps(
                {
                    "workflow_runs": [
                        _raw_run(id=1, created_at="2026-06-10T00:00:00Z"),
                        _raw_run(id=2, created_at="2026-05-01T00:00:00Z"),
                    ]
                }
            )
        )
        since = datetime(2026, 6, 1, tzinfo=timezone.utc)

        runs, _ = fetch_workflow_runs(repo_path=tmp_path, since=since)

        assert [run.run_id for run in runs] == [1]
        assert "?created=>=2026-06-01&per_page=100&page=1" in mock_run.call_args.args[0][-1]


class TestGetFilesChanged:
    @patch("black_box_unlock.cicd.github_actions.run_git")
    def test_returns_nonempty_paths_from_the_analyzed_repo(self, mock_git, tmp_path):
        mock_git.return_value = "src/main.py\n\ntests/test_main.py\n"

        files = get_files_changed("abc123", repo_path=tmp_path)

        assert files == ["src/main.py", "tests/test_main.py"]
        mock_git.assert_called_once_with(
            tmp_path, ["show", "--name-only", "--format=", "-m", "--first-parent", "abc123"]
        )

    @patch("black_box_unlock.cicd.github_actions.run_git")
    def test_invalid_sha_propagates_to_collector(self, mock_git):
        mock_git.side_effect = subprocess.CalledProcessError(128, ["git", "show"])

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
        assert endpoint.endswith("/runs/123/jobs?filter=all&per_page=100&page=1")
        assert mock_run.call_args.kwargs["cwd"] == tmp_path
