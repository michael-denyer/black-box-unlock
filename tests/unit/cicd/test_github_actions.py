"""Tests for GitHub Actions CI/CD integration."""

import json
from unittest.mock import MagicMock, patch

from black_box_unlock.cicd.github_actions import (
    fetch_workflow_runs,
    parse_workflow_runs,
)
from black_box_unlock.cicd.models import WorkflowRun


class TestParseWorkflowRuns:
    """Tests for parsing gh CLI JSON output."""

    def test_parses_successful_run(self):
        """Parses a successful workflow run from JSON."""
        gh_json = [
            {
                "databaseId": 123,
                "workflowName": "CI",
                "headSha": "abc123def",
                "conclusion": "success",
                "createdAt": "2026-01-26T10:00:00Z",
            }
        ]
        runs = parse_workflow_runs(gh_json)
        assert len(runs) == 1
        assert runs[0].run_id == 123
        assert runs[0].workflow_name == "CI"
        assert runs[0].commit_sha == "abc123def"
        assert runs[0].conclusion == "success"

    def test_parses_failed_run(self):
        """Parses a failed workflow run from JSON."""
        gh_json = [
            {
                "databaseId": 456,
                "workflowName": "Tests",
                "headSha": "def456ghi",
                "conclusion": "failure",
                "createdAt": "2026-01-26T11:00:00Z",
            }
        ]
        runs = parse_workflow_runs(gh_json)
        assert len(runs) == 1
        assert runs[0].is_failure is True

    def test_parses_multiple_runs(self):
        """Parses multiple workflow runs."""
        gh_json = [
            {
                "databaseId": 1,
                "workflowName": "CI",
                "headSha": "aaa",
                "conclusion": "success",
                "createdAt": "2026-01-26T10:00:00Z",
            },
            {
                "databaseId": 2,
                "workflowName": "CI",
                "headSha": "bbb",
                "conclusion": "failure",
                "createdAt": "2026-01-26T11:00:00Z",
            },
        ]
        runs = parse_workflow_runs(gh_json)
        assert len(runs) == 2

    def test_empty_list_returns_empty(self):
        """Empty JSON list returns empty result."""
        runs = parse_workflow_runs([])
        assert runs == []


class TestFetchWorkflowRuns:
    """Tests for fetching runs via gh CLI."""

    @patch("black_box_unlock.cicd.github_actions.subprocess.run")
    def test_calls_gh_with_correct_args(self, mock_run):
        """Calls gh run list with correct JSON fields."""
        mock_run.return_value = MagicMock(
            stdout="[]",
            returncode=0,
        )
        fetch_workflow_runs(limit=50)

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "gh" in args
        assert "run" in args
        assert "list" in args
        assert "--json" in args

    @patch("black_box_unlock.cicd.github_actions.subprocess.run")
    def test_returns_parsed_workflow_runs(self, mock_run):
        """Returns list of WorkflowRun objects."""
        gh_output = json.dumps(
            [
                {
                    "databaseId": 999,
                    "workflowName": "CI",
                    "headSha": "xyz",
                    "conclusion": "success",
                    "createdAt": "2026-01-26T12:00:00Z",
                }
            ]
        )
        mock_run.return_value = MagicMock(stdout=gh_output, returncode=0)

        runs = fetch_workflow_runs(limit=10)
        assert len(runs) == 1
        assert isinstance(runs[0], WorkflowRun)
        assert runs[0].run_id == 999
