"""Tests for GitHub Actions CI/CD integration."""

import json
import subprocess
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from black_box_unlock.cicd.github_actions import (
    aggregate_file_failures,
    build_failures_from_runs,
    fetch_workflow_runs,
    get_files_changed,
    parse_workflow_runs,
)
from black_box_unlock.cicd.models import BuildFailure, WorkflowRun


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


class TestGetFilesChanged:
    """Tests for getting files changed in a commit."""

    @patch("black_box_unlock.cicd.github_actions.subprocess.run")
    def test_returns_list_of_files(self, mock_run):
        """Returns list of files from git show output."""
        mock_run.return_value = MagicMock(
            stdout="src/main.py\ntests/test_main.py\n",
            returncode=0,
        )
        files = get_files_changed("abc123")
        assert files == ["src/main.py", "tests/test_main.py"]

    @patch("black_box_unlock.cicd.github_actions.subprocess.run")
    def test_filters_empty_lines(self, mock_run):
        """Filters out empty lines from output."""
        mock_run.return_value = MagicMock(
            stdout="src/main.py\n\n\n",
            returncode=0,
        )
        files = get_files_changed("abc123")
        assert files == ["src/main.py"]

    @patch("black_box_unlock.cicd.github_actions.subprocess.run")
    def test_calls_git_show_with_name_only(self, mock_run):
        """Calls git show with --name-only flag."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        get_files_changed("abc123")

        args = mock_run.call_args[0][0]
        assert "git" in args
        assert "show" in args
        assert "--name-only" in args
        assert "abc123" in args

    @patch("black_box_unlock.cicd.github_actions.subprocess.run")
    def test_raises_on_invalid_sha(self, mock_run):
        """Raises CalledProcessError for invalid SHA."""
        mock_run.side_effect = subprocess.CalledProcessError(128, "git")
        with pytest.raises(subprocess.CalledProcessError):
            get_files_changed("invalid_sha")


class TestBuildFailuresFromRuns:
    """Tests for building failure objects with file attribution."""

    @patch("black_box_unlock.cicd.github_actions.get_files_changed")
    def test_creates_failure_for_failed_run(self, mock_get_files):
        """Creates BuildFailure for each failed run."""
        mock_get_files.return_value = ["src/broken.py"]
        runs = [
            WorkflowRun(
                run_id=1,
                workflow_name="CI",
                commit_sha="abc",
                conclusion="failure",
                created_at=datetime.now(timezone.utc),
            )
        ]
        failures = build_failures_from_runs(runs)
        assert len(failures) == 1
        assert failures[0].run_id == 1
        assert failures[0].files_changed == ["src/broken.py"]

    @patch("black_box_unlock.cicd.github_actions.get_files_changed")
    def test_skips_successful_runs(self, mock_get_files):
        """Does not create failures for successful runs."""
        runs = [
            WorkflowRun(
                run_id=1,
                workflow_name="CI",
                commit_sha="abc",
                conclusion="success",
                created_at=datetime.now(timezone.utc),
            )
        ]
        failures = build_failures_from_runs(runs)
        assert len(failures) == 0
        mock_get_files.assert_not_called()

    @patch("black_box_unlock.cicd.github_actions.get_files_changed")
    def test_handles_multiple_failures(self, mock_get_files):
        """Handles multiple failed runs."""
        mock_get_files.side_effect = [["a.py"], ["b.py"]]
        runs = [
            WorkflowRun(
                run_id=1,
                workflow_name="CI",
                commit_sha="aaa",
                conclusion="failure",
                created_at=datetime.now(timezone.utc),
            ),
            WorkflowRun(
                run_id=2,
                workflow_name="CI",
                commit_sha="bbb",
                conclusion="failure",
                created_at=datetime.now(timezone.utc),
            ),
        ]
        failures = build_failures_from_runs(runs)
        assert len(failures) == 2
        assert failures[0].files_changed == ["a.py"]
        assert failures[1].files_changed == ["b.py"]

    @patch("black_box_unlock.cicd.github_actions.get_files_changed")
    def test_propagates_git_error(self, mock_get_files):
        """Propagates CalledProcessError when git command fails."""
        mock_get_files.side_effect = subprocess.CalledProcessError(128, "git")
        runs = [
            WorkflowRun(
                run_id=1,
                workflow_name="CI",
                commit_sha="abc",
                conclusion="failure",
                created_at=datetime.now(timezone.utc),
            )
        ]
        with pytest.raises(subprocess.CalledProcessError):
            build_failures_from_runs(runs)


class TestAggregateFileFailures:
    """Tests for aggregating failures per file."""

    def test_counts_failures_per_file(self):
        """Counts how many failures touched each file."""
        failures = [
            BuildFailure(
                run_id=1,
                workflow_name="CI",
                commit_sha="a",
                files_changed=["src/a.py", "src/b.py"],
                failed_at=datetime.now(timezone.utc),
                conclusion="failure",
            ),
            BuildFailure(
                run_id=2,
                workflow_name="CI",
                commit_sha="b",
                files_changed=["src/a.py"],
                failed_at=datetime.now(timezone.utc),
                conclusion="failure",
            ),
        ]
        stats = aggregate_file_failures(failures)
        assert stats["src/a.py"] == 2
        assert stats["src/b.py"] == 1

    def test_empty_failures_returns_empty_dict(self):
        """Empty failures list returns empty dict."""
        stats = aggregate_file_failures([])
        assert stats == {}
