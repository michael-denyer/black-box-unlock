"""Tests for CI/CD data models."""

from datetime import datetime, timezone

from black_box_unlock.cicd.models import BuildFailure, WorkflowRun


class TestWorkflowRun:
    """Tests for WorkflowRun model."""

    def test_creates_workflow_run_with_required_fields(self):
        """Creates WorkflowRun with all required fields."""
        run = WorkflowRun(
            run_id=123,
            workflow_name="CI",
            commit_sha="abc123",
            conclusion="success",
            created_at=datetime(2026, 1, 26, tzinfo=timezone.utc),
        )
        assert run.run_id == 123
        assert run.workflow_name == "CI"
        assert run.commit_sha == "abc123"
        assert run.conclusion == "success"

    def test_is_failure_returns_true_for_failure_conclusion(self):
        """is_failure returns True when conclusion is 'failure'."""
        run = WorkflowRun(
            run_id=1,
            workflow_name="CI",
            commit_sha="abc",
            conclusion="failure",
            created_at=datetime.now(timezone.utc),
        )
        assert run.is_failure is True

    def test_is_failure_returns_false_for_success(self):
        """is_failure returns False when conclusion is 'success'."""
        run = WorkflowRun(
            run_id=1,
            workflow_name="CI",
            commit_sha="abc",
            conclusion="success",
            created_at=datetime.now(timezone.utc),
        )
        assert run.is_failure is False

    def test_is_failure_returns_true_for_timed_out(self):
        """is_failure returns True when conclusion is 'timed_out'."""
        run = WorkflowRun(
            run_id=1,
            workflow_name="CI",
            commit_sha="abc",
            conclusion="timed_out",
            created_at=datetime.now(timezone.utc),
        )
        assert run.is_failure is True


class TestBuildFailure:
    """Tests for BuildFailure model."""

    def test_creates_build_failure_with_files_changed(self):
        """Creates BuildFailure with list of files changed."""
        failure = BuildFailure(
            run_id=456,
            workflow_name="CI",
            commit_sha="def456",
            files_changed=["src/main.py", "tests/test_main.py"],
            failed_at=datetime(2026, 1, 26, tzinfo=timezone.utc),
            conclusion="failure",
        )
        assert failure.run_id == 456
        assert failure.conclusion == "failure"
        assert len(failure.files_changed) == 2
        assert "src/main.py" in failure.files_changed
