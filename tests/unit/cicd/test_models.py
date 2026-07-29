"""Tests for typed CI input and result models."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from black_box_unlock.cicd.models import CIAnalysis, WorkflowJob, WorkflowRun
from black_box_unlock.core.models import SignalState, SignalStatus


class TestWorkflowRun:
    def test_failure_conclusions(self):
        common = {
            "run_id": 123,
            "workflow_name": "CI",
            "commit_sha": "abc123",
            "created_at": datetime(2026, 1, 26, tzinfo=timezone.utc),
        }

        assert WorkflowRun(**common, conclusion="failure").is_failure is True
        assert WorkflowRun(**common, conclusion="timed_out").is_failure is True
        assert WorkflowRun(**common, conclusion="success").is_failure is False

    def test_attempt_must_be_positive(self):
        with pytest.raises(ValidationError):
            WorkflowRun(
                run_id=123,
                workflow_name="CI",
                commit_sha="abc123",
                conclusion="success",
                created_at=datetime(2026, 1, 26, tzinfo=timezone.utc),
                run_attempt=0,
            )


class TestWorkflowJob:
    def test_parses_nested_step_timestamps(self):
        job = WorkflowJob.model_validate(
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
        )

        assert job.run_attempt == 2
        assert job.steps[0].completed_at == datetime(2026, 6, 2, 10, 0, tzinfo=timezone.utc)


class TestCIAnalysis:
    def test_empty_available_result_is_distinct_from_disabled(self):
        result = CIAnalysis(status=SignalStatus(state=SignalState.available))

        assert result.status.state is SignalState.available
        assert result.file_failures == {}
        assert result.flaky_steps == []
