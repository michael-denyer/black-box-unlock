"""Tests for flaky step detection."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from black_box_unlock.cicd.models import FlakyStep, StepResult
from black_box_unlock.core.models import AnalysisResult, AnalysisSummary, FlakyStepSummary


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
            total_runs=20,
            failures=5,
            flaky_count=3,
        )
        assert step.job_name == "test (3.10)"
        assert step.total_runs == 20
        assert step.flaky_count == 3

    def test_flaky_rate_calculation(self):
        """Calculates flaky_rate as flaky_count / total_runs."""
        step = FlakyStep(
            job_name="test",
            step_name="Run tests",
            first_seen=datetime(2026, 1, 20, tzinfo=timezone.utc),
            last_seen=datetime(2026, 1, 26, tzinfo=timezone.utc),
            total_runs=20,
            failures=5,
            flaky_count=4,
        )
        assert step.flaky_rate == 0.2  # 4/20

    def test_flaky_rate_zero_when_no_runs(self):
        """Returns 0 flaky_rate when total_runs is 0."""
        step = FlakyStep(
            job_name="test",
            step_name="Run tests",
            first_seen=datetime(2026, 1, 20, tzinfo=timezone.utc),
            last_seen=datetime(2026, 1, 26, tzinfo=timezone.utc),
            total_runs=0,
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
            total_runs=10,
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
            total_runs=10,
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
        """Calls gh api with runs/{id}/jobs endpoint."""
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
        # Should include runs/123/jobs in the endpoint
        endpoint_arg = [a for a in args if "123" in a and "jobs" in a]
        assert len(endpoint_arg) == 1

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


class TestDetectFlakySteps:
    """Tests for flaky step detection logic."""

    def test_detects_flaky_when_retry_passes(self):
        """Detects flakiness when same commit fails then passes on retry."""
        from black_box_unlock.cicd.github_actions import detect_flaky_steps

        # Simulate: commit abc, attempt 1 failed, attempt 2 passed
        runs = [
            {
                "id": 1,
                "head_sha": "abc123",
                "run_attempt": 1,
                "conclusion": "failure",
                "workflow_name": "CI",
            },
            {
                "id": 2,
                "head_sha": "abc123",
                "run_attempt": 2,
                "conclusion": "success",
                "workflow_name": "CI",
            },
        ]

        # Mock job data showing step failed then passed
        job_data = {
            1: [
                {
                    "name": "test",
                    "steps": [
                        {
                            "name": "Run tests",
                            "conclusion": "failure",
                            "completed_at": "2026-01-26T10:00:00Z",
                        }
                    ],
                }
            ],
            2: [
                {
                    "name": "test",
                    "steps": [
                        {
                            "name": "Run tests",
                            "conclusion": "success",
                            "completed_at": "2026-01-26T10:05:00Z",
                        }
                    ],
                }
            ],
        }

        with patch("black_box_unlock.cicd.github_actions.fetch_jobs_for_run") as mock_fetch:
            mock_fetch.side_effect = lambda run_id: job_data[run_id]
            flaky_steps = detect_flaky_steps(runs)

        assert len(flaky_steps) == 1
        assert flaky_steps[0].step_name == "Run tests"
        assert flaky_steps[0].flaky_count == 1

    def test_no_flaky_when_consistently_passes(self):
        """No flakiness detected when step always passes."""
        from black_box_unlock.cicd.github_actions import detect_flaky_steps

        runs = [
            {
                "id": 1,
                "head_sha": "abc",
                "run_attempt": 1,
                "conclusion": "success",
                "workflow_name": "CI",
            },
            {
                "id": 2,
                "head_sha": "def",
                "run_attempt": 1,
                "conclusion": "success",
                "workflow_name": "CI",
            },
        ]

        job_data = {
            1: [
                {
                    "name": "test",
                    "steps": [
                        {
                            "name": "Run tests",
                            "conclusion": "success",
                            "completed_at": "2026-01-26T10:00:00Z",
                        }
                    ],
                }
            ],
            2: [
                {
                    "name": "test",
                    "steps": [
                        {
                            "name": "Run tests",
                            "conclusion": "success",
                            "completed_at": "2026-01-26T11:00:00Z",
                        }
                    ],
                }
            ],
        }

        with patch("black_box_unlock.cicd.github_actions.fetch_jobs_for_run") as mock_fetch:
            mock_fetch.side_effect = lambda run_id: job_data[run_id]
            flaky_steps = detect_flaky_steps(runs)

        # Should return empty or only steps with high failure rate
        flaky = [s for s in flaky_steps if s.flaky_count > 0]
        assert len(flaky) == 0

    def test_no_flaky_when_consistently_fails(self):
        """No flakiness when step always fails (it's broken, not flaky)."""
        from black_box_unlock.cicd.github_actions import detect_flaky_steps

        runs = [
            {
                "id": 1,
                "head_sha": "abc",
                "run_attempt": 1,
                "conclusion": "failure",
                "workflow_name": "CI",
            },
            {
                "id": 2,
                "head_sha": "abc",
                "run_attempt": 2,
                "conclusion": "failure",
                "workflow_name": "CI",
            },
        ]

        job_data = {
            1: [
                {
                    "name": "test",
                    "steps": [
                        {
                            "name": "Run tests",
                            "conclusion": "failure",
                            "completed_at": "2026-01-26T10:00:00Z",
                        }
                    ],
                }
            ],
            2: [
                {
                    "name": "test",
                    "steps": [
                        {
                            "name": "Run tests",
                            "conclusion": "failure",
                            "completed_at": "2026-01-26T10:05:00Z",
                        }
                    ],
                }
            ],
        }

        with patch("black_box_unlock.cicd.github_actions.fetch_jobs_for_run") as mock_fetch:
            mock_fetch.side_effect = lambda run_id: job_data[run_id]
            flaky_steps = detect_flaky_steps(runs)

        # Should have failures but no flaky_count
        flaky = [s for s in flaky_steps if s.flaky_count > 0]
        assert len(flaky) == 0

    def test_tracks_first_and_last_seen(self):
        """Tracks first_seen and last_seen timestamps for steps."""
        from black_box_unlock.cicd.github_actions import detect_flaky_steps

        runs = [
            {
                "id": 1,
                "head_sha": "abc",
                "run_attempt": 1,
                "conclusion": "failure",
                "workflow_name": "CI",
            },
            {
                "id": 2,
                "head_sha": "abc",
                "run_attempt": 2,
                "conclusion": "success",
                "workflow_name": "CI",
            },
        ]

        job_data = {
            1: [
                {
                    "name": "test",
                    "steps": [
                        {
                            "name": "Run tests",
                            "conclusion": "failure",
                            "completed_at": "2026-01-20T10:00:00Z",
                        }
                    ],
                }
            ],
            2: [
                {
                    "name": "test",
                    "steps": [
                        {
                            "name": "Run tests",
                            "conclusion": "success",
                            "completed_at": "2026-01-26T10:00:00Z",
                        }
                    ],
                }
            ],
        }

        with patch("black_box_unlock.cicd.github_actions.fetch_jobs_for_run") as mock_fetch:
            mock_fetch.side_effect = lambda run_id: job_data[run_id]
            flaky_steps = detect_flaky_steps(runs)

        assert len(flaky_steps) == 1
        assert flaky_steps[0].first_seen.day == 20
        assert flaky_steps[0].last_seen.day == 26

    def test_empty_runs_returns_empty_list(self):
        """Empty runs list returns empty flaky steps."""
        from black_box_unlock.cicd.github_actions import detect_flaky_steps

        flaky_steps = detect_flaky_steps([])
        assert flaky_steps == []


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
            total_runs=20,
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
            total_runs=10,
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
