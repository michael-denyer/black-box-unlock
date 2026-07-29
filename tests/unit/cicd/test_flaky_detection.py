"""Tests for flaky-step computation over typed workflow jobs."""

from datetime import datetime, timezone

from black_box_unlock.cicd.github_actions import (
    flaky_steps_from_jobs,
    summarize_flaky_steps,
)
from black_box_unlock.cicd.models import FlakyStep, WorkflowJob


def _job(
    run_attempt: int,
    steps: list[tuple[str, str]],
    name: str = "test (3.11)",
) -> WorkflowJob:
    return WorkflowJob.model_validate(
        {
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
    )


class TestFlakyStepsFromJobs:
    def test_fail_then_pass_across_attempts_is_flaky(self):
        step = flaky_steps_from_jobs(
            [
                _job(1, [("Run tests", "failure"), ("Checkout", "success")]),
                _job(2, [("Run tests", "success"), ("Checkout", "success")]),
            ]
        )[0]

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

    def test_all_green_and_skipped_steps_are_not_flaky(self):
        jobs = [
            _job(1, [("Run tests", "success"), ("Deploy", "skipped")]),
            _job(2, [("Run tests", "success"), ("Deploy", "skipped")]),
        ]

        assert flaky_steps_from_jobs(jobs) == []

    def test_two_failures_before_success_both_count(self):
        step = flaky_steps_from_jobs(
            [
                _job(1, [("Run tests", "failure")]),
                _job(2, [("Run tests", "failure")]),
                _job(3, [("Run tests", "success")]),
            ]
        )[0]

        assert step.flaky_count == 2
        assert step.failures == 2
        assert step.total_attempts == 3
        assert step.first_seen == datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
        assert step.last_seen == datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc)

    def test_same_attempt_fail_and_pass_is_not_flaky(self):
        jobs = [
            _job(1, [("Run tests", "failure")]),
            _job(1, [("Run tests", "success")]),
        ]

        assert flaky_steps_from_jobs(jobs) == []


class TestSummarizeFlakySteps:
    def _step(
        self,
        *,
        first: datetime,
        last: datetime,
        attempts: int,
        failures: int,
        flaky: int,
        step: str = "Run tests",
    ) -> FlakyStep:
        return FlakyStep(
            job_name="test (3.11)",
            step_name=step,
            first_seen=first,
            last_seen=last,
            total_attempts=attempts,
            failures=failures,
            flaky_count=flaky,
        )

    def test_merges_counts_and_seen_window(self):
        result = summarize_flaky_steps(
            [
                self._step(
                    first=datetime(2026, 6, 1, tzinfo=timezone.utc),
                    last=datetime(2026, 6, 2, tzinfo=timezone.utc),
                    attempts=2,
                    failures=1,
                    flaky=1,
                ),
                self._step(
                    first=datetime(2026, 6, 3, tzinfo=timezone.utc),
                    last=datetime(2026, 6, 4, tzinfo=timezone.utc),
                    attempts=3,
                    failures=2,
                    flaky=2,
                ),
            ]
        )

        assert len(result) == 1
        merged = result[0]
        assert (merged.total_attempts, merged.failures, merged.flaky_count) == (5, 3, 3)
        assert merged.first_seen == datetime(2026, 6, 1, tzinfo=timezone.utc)
        assert merged.last_seen == datetime(2026, 6, 4, tzinfo=timezone.utc)

    def test_distinct_steps_stay_separate_and_sorted(self):
        timestamp = datetime(2026, 6, 1, tzinfo=timezone.utc)
        result = summarize_flaky_steps(
            [
                self._step(
                    first=timestamp,
                    last=timestamp,
                    attempts=2,
                    failures=1,
                    flaky=1,
                    step="test",
                ),
                self._step(
                    first=timestamp,
                    last=timestamp,
                    attempts=2,
                    failures=1,
                    flaky=1,
                    step="lint",
                ),
            ]
        )

        assert [step.step_name for step in result] == ["lint", "test"]

    def test_empty_returns_empty(self):
        assert summarize_flaky_steps([]) == []
