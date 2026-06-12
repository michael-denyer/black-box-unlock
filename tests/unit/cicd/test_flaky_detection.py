"""Unit tests for flaky step detection (real GitHub API shapes)."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from black_box_unlock.cicd.github_actions import (
    detect_flaky_steps,
    flaky_steps_from_jobs,
)
from black_box_unlock.cicd.models import FlakyStep, StepResult
from black_box_unlock.core.models import AnalysisResult, AnalysisSummary, FlakyStepSummary


def _job(run_attempt: int, steps: list[tuple[str, str]], name: str = "test (3.11)") -> dict:
    """A job dict as returned by /actions/runs/{id}/jobs?filter=all."""
    return {
        "name": name,
        "run_attempt": run_attempt,
        "steps": [
            {
                "name": step_name,
                "conclusion": conclusion,
                "completed_at": f"2026-06-0{run_attempt}T10:00:00Z",
            }
            for step_name, conclusion in steps
        ],
    }


class TestFlakyStepsFromJobs:
    def test_fail_then_pass_across_attempts_is_flaky(self):
        jobs = [
            _job(1, [("Run tests", "failure"), ("Checkout", "success")]),
            _job(2, [("Run tests", "success"), ("Checkout", "success")]),
        ]

        flaky = flaky_steps_from_jobs(jobs)

        assert len(flaky) == 1
        step = flaky[0]
        assert step.step_name == "Run tests"
        assert step.job_name == "test (3.11)"
        assert step.flaky_count == 1
        assert step.failures == 1
        assert step.total_attempts == 2

    def test_consistent_failure_is_not_flaky(self):
        jobs = [
            _job(1, [("Run tests", "failure")]),
            _job(2, [("Run tests", "failure")]),
        ]

        assert flaky_steps_from_jobs(jobs) == []

    def test_all_green_is_not_flaky(self):
        jobs = [
            _job(1, [("Run tests", "success")]),
            _job(2, [("Run tests", "success")]),
        ]

        assert flaky_steps_from_jobs(jobs) == []

    def test_skipped_steps_ignored(self):
        jobs = [
            _job(1, [("Deploy", "skipped")]),
            _job(2, [("Deploy", "skipped")]),
        ]

        assert flaky_steps_from_jobs(jobs) == []

    def test_tracks_first_and_last_seen(self):
        jobs = [
            _job(1, [("Run tests", "failure")]),
            _job(2, [("Run tests", "success")]),
        ]

        step = flaky_steps_from_jobs(jobs)[0]
        assert step.first_seen.day == 1
        assert step.last_seen.day == 2

    def test_two_failures_before_success_both_count(self):
        """F,F,S yields flaky_count 2: each failed attempt preceding a later success counts."""
        jobs = [
            _job(1, [("Run tests", "failure")]),
            _job(2, [("Run tests", "failure")]),
            _job(3, [("Run tests", "success")]),
        ]

        step = flaky_steps_from_jobs(jobs)[0]
        assert step.flaky_count == 2
        assert step.failures == 2
        assert step.total_attempts == 3

    def test_same_attempt_fail_and_pass_is_not_flaky(self):
        """A failure and a success in the SAME attempt is not a retry recovery.

        Matrix jobs that share a name can report both outcomes under one
        run_attempt. The flaky scan requires a success in a STRICTLY LATER
        attempt, so a same-attempt pair must not count as flaky.
        """
        jobs = [
            {
                "name": "test (3.11)",
                "run_attempt": 1,
                "steps": [
                    {
                        "name": "Run tests",
                        "conclusion": "failure",
                        "completed_at": "2026-06-01T10:00:00Z",
                    }
                ],
            },
            {
                "name": "test (3.11)",
                "run_attempt": 1,
                "steps": [
                    {
                        "name": "Run tests",
                        "conclusion": "success",
                        "completed_at": "2026-06-01T10:05:00Z",
                    }
                ],
            },
        ]

        assert flaky_steps_from_jobs(jobs) == []


class TestDetectFlakySteps:
    @patch("black_box_unlock.cicd.github_actions.fetch_jobs_for_run")
    @patch("black_box_unlock.cicd.github_actions.fetch_all_runs")
    def test_only_fetches_jobs_for_rerun_runs(self, mock_runs, mock_jobs):
        """Runs with run_attempt == 1 were never re-run - no jobs fetch needed."""
        mock_runs.return_value = [
            {"id": 1, "run_attempt": 1, "name": "CI"},
            {"id": 2, "run_attempt": 3, "name": "CI"},
        ]
        mock_jobs.return_value = [
            _job(1, [("Run tests", "failure")]),
            _job(3, [("Run tests", "success")]),
        ]

        flaky = detect_flaky_steps(repo_path=Path("."), limit=50)

        mock_jobs.assert_called_once_with(2, repo_path=Path("."))
        assert len(flaky) == 1
        assert flaky[0].flaky_count == 1

    @patch("black_box_unlock.cicd.github_actions.fetch_all_runs")
    def test_no_reruns_means_no_flaky_steps(self, mock_runs):
        mock_runs.return_value = [{"id": 1, "run_attempt": 1, "name": "CI"}]

        assert detect_flaky_steps(repo_path=Path("."), limit=50) == []


class TestStepResultModel:
    """Tests for StepResult model."""

    def test_creates_step_result(self):
        """Creates StepResult with all required fields."""
        result = StepResult(
            job_name="test (3.10)",
            step_name="Run tests",
            conclusion="success",
            run_id=123,
            attempt=1,
            commit_sha="abc123",
            executed_at=datetime(2026, 1, 26, 10, 0, 0, tzinfo=timezone.utc),
        )
        assert result.job_name == "test (3.10)"
        assert result.step_name == "Run tests"
        assert result.conclusion == "success"
        assert result.attempt == 1

    def test_step_result_with_failure_conclusion(self):
        """StepResult can have failure conclusion."""
        result = StepResult(
            job_name="test (3.10)",
            step_name="Run tests",
            conclusion="failure",
            run_id=123,
            attempt=1,
            commit_sha="abc123",
            executed_at=datetime(2026, 1, 26, 10, 0, 0, tzinfo=timezone.utc),
        )
        assert result.conclusion == "failure"


class TestFlakyStepModel:
    """Tests for FlakyStep model."""

    def test_creates_flaky_step(self):
        """Creates FlakyStep with all required fields."""
        step = FlakyStep(
            job_name="test (3.10)",
            step_name="Run tests",
            first_seen=datetime(2026, 1, 20, tzinfo=timezone.utc),
            last_seen=datetime(2026, 1, 26, tzinfo=timezone.utc),
            total_attempts=20,
            failures=5,
            flaky_count=3,
        )
        assert step.job_name == "test (3.10)"
        assert step.total_attempts == 20
        assert step.flaky_count == 3

    def test_flaky_rate_calculation(self):
        """Calculates flaky_rate as flaky_count / total_attempts."""
        step = FlakyStep(
            job_name="test",
            step_name="Run tests",
            first_seen=datetime(2026, 1, 20, tzinfo=timezone.utc),
            last_seen=datetime(2026, 1, 26, tzinfo=timezone.utc),
            total_attempts=20,
            failures=5,
            flaky_count=4,
        )
        assert step.flaky_rate == 0.2  # 4/20

    def test_flaky_rate_zero_when_no_runs(self):
        """Returns 0 flaky_rate when total_attempts is 0."""
        step = FlakyStep(
            job_name="test",
            step_name="Run tests",
            first_seen=datetime(2026, 1, 20, tzinfo=timezone.utc),
            last_seen=datetime(2026, 1, 26, tzinfo=timezone.utc),
            total_attempts=0,
            failures=0,
            flaky_count=0,
        )
        assert step.flaky_rate == 0.0

    def test_is_active_true_when_recent(self):
        """is_active is True when last_seen is within 7 days."""
        now = datetime.now(timezone.utc)
        step = FlakyStep(
            job_name="test",
            step_name="Run tests",
            first_seen=datetime(2026, 1, 20, tzinfo=timezone.utc),
            last_seen=now,
            total_attempts=10,
            failures=1,
            flaky_count=1,
        )
        assert step.is_active is True

    def test_is_active_false_when_stale(self):
        """is_active is False when last_seen is older than 7 days."""
        step = FlakyStep(
            job_name="test",
            step_name="Run tests",
            first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc),
            last_seen=datetime(2026, 1, 10, tzinfo=timezone.utc),  # Old date
            total_attempts=10,
            failures=1,
            flaky_count=1,
        )
        assert step.is_active is False


class TestFetchAllRuns:
    """Tests for fetching all workflow runs via REST API."""

    @patch("black_box_unlock.cicd.github_actions.subprocess.run")
    def test_calls_gh_api_with_correct_endpoint(self, mock_run):
        """Calls gh api with actions/runs endpoint."""
        from black_box_unlock.cicd.github_actions import fetch_all_runs

        mock_run.return_value = MagicMock(
            stdout='{"workflow_runs": []}',
            returncode=0,
        )
        fetch_all_runs(limit=50)

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "gh" in args
        assert "api" in args
        # Should include actions/runs in the endpoint
        endpoint_arg = [a for a in args if "actions/runs" in a]
        assert len(endpoint_arg) == 1

    @patch("black_box_unlock.cicd.github_actions.subprocess.run")
    def test_returns_workflow_runs_list(self, mock_run):
        """Returns list of workflow run dicts."""
        from black_box_unlock.cicd.github_actions import fetch_all_runs

        mock_run.return_value = MagicMock(
            stdout=json.dumps(
                {
                    "workflow_runs": [
                        {"id": 123, "head_sha": "abc", "run_attempt": 1, "conclusion": "success"}
                    ]
                }
            ),
            returncode=0,
        )
        runs = fetch_all_runs(limit=10)
        assert len(runs) == 1
        assert runs[0]["id"] == 123


class TestFetchJobsForRun:
    """Tests for fetching jobs+steps for a single run."""

    @patch("black_box_unlock.cicd.github_actions.subprocess.run")
    def test_calls_gh_api_with_jobs_endpoint(self, mock_run):
        """Calls gh api with runs/{id}/jobs endpoint including filter=all."""
        from black_box_unlock.cicd.github_actions import fetch_jobs_for_run

        mock_run.return_value = MagicMock(
            stdout='{"jobs": []}',
            returncode=0,
        )
        fetch_jobs_for_run(run_id=123)

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "gh" in args
        assert "api" in args
        # Should include runs/123/jobs in the endpoint, across all attempts
        endpoint_arg = [a for a in args if "123" in a and "jobs" in a]
        assert len(endpoint_arg) == 1
        assert "filter=all" in endpoint_arg[0]
        assert "per_page=100" in endpoint_arg[0]

    @patch("black_box_unlock.cicd.github_actions.subprocess.run")
    def test_returns_jobs_with_steps(self, mock_run):
        """Returns list of job dicts with steps."""
        from black_box_unlock.cicd.github_actions import fetch_jobs_for_run

        mock_run.return_value = MagicMock(
            stdout=json.dumps(
                {
                    "jobs": [
                        {
                            "name": "test (3.10)",
                            "conclusion": "success",
                            "steps": [{"name": "Run tests", "conclusion": "success", "number": 1}],
                        }
                    ]
                }
            ),
            returncode=0,
        )
        jobs = fetch_jobs_for_run(run_id=123)
        assert len(jobs) == 1
        assert jobs[0]["name"] == "test (3.10)"
        assert len(jobs[0]["steps"]) == 1


class TestAnalysisResultIntegration:
    """Tests for AnalysisResult including flaky_steps field."""

    def test_analysis_result_has_flaky_steps_field(self):
        """AnalysisResult includes flaky_steps field."""
        result = AnalysisResult(
            repo="test-repo",
            analyzed_days=30,
            generated_at=datetime.now(timezone.utc),
            files=[],
            summary=AnalysisSummary(total_files=0, high_risk_ownership=0, coupled_pairs=0),
            flaky_steps=[],
        )
        assert result.flaky_steps == []

    def test_analysis_result_with_flaky_steps(self):
        """AnalysisResult can contain FlakyStepSummary objects."""
        flaky = FlakyStepSummary(
            job_name="test (3.10)",
            step_name="Run tests",
            first_seen=datetime(2026, 1, 20, tzinfo=timezone.utc),
            last_seen=datetime(2026, 1, 26, tzinfo=timezone.utc),
            total_attempts=20,
            failures=5,
            flaky_count=3,
        )
        result = AnalysisResult(
            repo="test-repo",
            analyzed_days=30,
            generated_at=datetime.now(timezone.utc),
            files=[],
            summary=AnalysisSummary(total_files=0, high_risk_ownership=0, coupled_pairs=0),
            flaky_steps=[flaky],
        )
        assert len(result.flaky_steps) == 1
        assert result.flaky_steps[0].step_name == "Run tests"

    def test_analysis_result_serializes_flaky_steps(self):
        """AnalysisResult JSON serialization includes flaky_steps."""
        flaky = FlakyStepSummary(
            job_name="test",
            step_name="Run tests",
            first_seen=datetime(2026, 1, 20, tzinfo=timezone.utc),
            last_seen=datetime(2026, 1, 26, tzinfo=timezone.utc),
            total_attempts=10,
            failures=2,
            flaky_count=1,
        )
        result = AnalysisResult(
            repo="test-repo",
            analyzed_days=30,
            generated_at=datetime.now(timezone.utc),
            files=[],
            summary=AnalysisSummary(total_files=0, high_risk_ownership=0, coupled_pairs=0),
            flaky_steps=[flaky],
        )
        data = result.model_dump(mode="json")
        assert "flaky_steps" in data
        assert len(data["flaky_steps"]) == 1
        assert data["flaky_steps"][0]["flaky_rate"] == 0.1  # 1/10
