"""Unit tests for CLI commands."""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from black_box_unlock.cli import app
from black_box_unlock.core.exceptions import InsufficientHistoryError
from black_box_unlock.core.models import SignalStatus
from black_box_unlock.git.changes import WorkingTreeProvenance
from black_box_unlock.review import ChangeReview, ReviewParameters
from black_box_unlock.validation import MethodScore, RandomBaseline, ValidationReport

runner = CliRunner()


def _validation_result(
    repo: str = "demo", spearman: float | None = 0.62, insufficient: bool = False
) -> ValidationReport:
    return ValidationReport(
        repo=repo,
        days=730,
        split=0.5,
        cutoff=datetime(2025, 6, 12, tzinfo=timezone.utc),
        cutoff_sha="0123456789abcdef0123456789abcdef01234567",
        clock="committer",
        universe_size=120,
        train_commits=300,
        test_commits=280,
        test_bugfix_commits=90,
        test_bugfix_touches=200,
        bugfix_coverage=0.88,
        methods={
            "hotspot": MethodScore(spearman=spearman, top_decile_share=0.45, top_files=["a.py"])
        },
        random=RandomBaseline(
            draws=200,
            seed=1,
            spearman_mean=0.0,
            spearman_sd=0.1,
            top_decile_share_mean=0.1,
            top_decile_share_sd=0.03,
        ),
        p_value=0.005,
        insufficient_data=insufficient,
        insufficient_reasons=["5 universe files < 20"] if insufficient else [],
    )


class TestAnalyzeRepoCommand:
    """Tests for analyze-repo command."""

    def test_outputs_json_format(self):
        """--output=json produces JSON to stdout."""
        mock_result = MagicMock()
        mock_result.repo = "test-repo"
        mock_result.analyzed_days = 30
        mock_result.files = []
        mock_result.summary.total_files = 0
        mock_result.summary.high_risk_ownership = 0
        mock_result.summary.coupled_pairs = 0

        with patch("black_box_unlock.cli.run_analysis") as mock_analysis:
            mock_analysis.return_value = mock_result
            with patch("black_box_unlock.cli.export_to_json") as mock_export:
                mock_export.return_value = '{"repo": "test-repo"}'
                result = runner.invoke(app, ["analyze-repo", "--output", "json"])

        assert result.exit_code == 0
        assert '{"repo": "test-repo"}' in result.stdout

    def test_outputs_html_format(self):
        """--output=html produces HTML to stdout."""
        mock_result = MagicMock()
        mock_result.repo = "test-repo"

        with patch("black_box_unlock.cli.run_analysis") as mock_analysis:
            mock_analysis.return_value = mock_result
            with patch("black_box_unlock.cli.generate_html_report") as mock_html:
                mock_html.return_value = "<!DOCTYPE html><html></html>"
                result = runner.invoke(app, ["analyze-repo", "--output", "html"])

        assert result.exit_code == 0
        assert "<!DOCTYPE html>" in result.stdout

    def test_uses_days_option(self):
        """--days option is passed to run_analysis."""
        mock_result = MagicMock()
        mock_result.files = []
        mock_result.summary.total_files = 0

        with patch("black_box_unlock.cli.run_analysis") as mock_analysis:
            mock_analysis.return_value = mock_result
            with patch("black_box_unlock.cli.export_to_json") as mock_export:
                mock_export.return_value = "{}"
                runner.invoke(app, ["analyze-repo", "--days", "60", "--output", "json"])

        mock_analysis.assert_called_once()
        _, kwargs = mock_analysis.call_args
        assert kwargs.get("days") == 60

    def test_defaults_to_current_directory(self):
        """Uses current directory when no path specified."""
        mock_result = MagicMock()
        mock_result.files = []

        with patch("black_box_unlock.cli.run_analysis") as mock_analysis:
            mock_analysis.return_value = mock_result
            with patch("black_box_unlock.cli.export_to_json") as mock_export:
                mock_export.return_value = "{}"
                runner.invoke(app, ["analyze-repo", "--output", "json"])

        mock_analysis.assert_called_once()
        call_args = mock_analysis.call_args
        # First positional arg is repo_path
        assert call_args[0][0] == Path(".")

    def test_no_ci_flag_skips_ci_analysis(self):
        """--no-ci flag passes include_ci=False to run_analysis."""
        mock_result = MagicMock()
        mock_result.files = []

        with patch("black_box_unlock.cli.run_analysis") as mock_run_analysis:
            mock_run_analysis.return_value = mock_result
            with patch("black_box_unlock.cli.export_to_json") as mock_export:
                mock_export.return_value = "{}"
                result = runner.invoke(app, ["analyze-repo", "--no-ci"])

        assert result.exit_code == 0
        mock_run_analysis.assert_called_once()
        call_kwargs = mock_run_analysis.call_args[1]
        assert call_kwargs.get("include_ci") is False

    def test_repo_option_is_passed_to_run_analysis(self):
        """--repo option sets the repo path."""
        mock_result = MagicMock()
        mock_result.files = []

        with patch("black_box_unlock.cli.run_analysis") as mock_analysis:
            mock_analysis.return_value = mock_result
            with patch("black_box_unlock.cli.export_to_json") as mock_export:
                mock_export.return_value = "{}"
                runner.invoke(app, ["analyze-repo", "--repo", "/some/repo", "--output", "json"])

        assert mock_analysis.call_args[0][0] == Path("/some/repo")

    def test_coupling_options_build_the_policy(self, tmp_path):
        from black_box_unlock.core.models import CouplingPolicy

        (tmp_path / ".bbu.toml").write_text("[coupling]\nrequire_live_partner = false\n")
        with (
            patch("black_box_unlock.cli.run_analysis") as mock_analysis,
            patch("black_box_unlock.cli.is_shallow", return_value=False),
        ):
            mock_analysis.return_value = MagicMock()
            with patch("black_box_unlock.cli.export_to_json", return_value="{}"):
                result = runner.invoke(
                    app,
                    [
                        "analyze-repo",
                        "--repo",
                        str(tmp_path),
                        "--min-coupling",
                        "0.5",
                        "--min-shared-revisions",
                        "3",
                        "--max-changeset-size",
                        "80",
                    ],
                )

        assert result.exit_code == 0
        assert mock_analysis.call_args.kwargs["policy"] == CouplingPolicy(
            min_ratio=0.5,
            min_shared_revisions=3,
            max_changeset_size=80,
            require_live_partner=False,
        )

    def test_ci_included_by_default(self):
        """Without --no-ci, include_ci defaults to True."""
        mock_result = MagicMock()
        mock_result.files = []

        with patch("black_box_unlock.cli.run_analysis") as mock_run_analysis:
            mock_run_analysis.return_value = mock_result
            with patch("black_box_unlock.cli.export_to_json") as mock_export:
                mock_export.return_value = "{}"
                result = runner.invoke(app, ["analyze-repo"])

        assert result.exit_code == 0
        mock_run_analysis.assert_called_once()
        call_kwargs = mock_run_analysis.call_args[1]
        assert call_kwargs.get("include_ci") is True


class TestAnalyzeRepoErrorHandling:
    """Tests for clean error reporting from analyze-repo."""

    def test_missing_git_prints_clean_error_not_traceback(self):
        """GitToolNotFoundError surfaces as an error message with exit code 1."""
        from black_box_unlock.core.exceptions import GitToolNotFoundError

        with patch("black_box_unlock.cli.run_analysis") as mock_analysis:
            mock_analysis.side_effect = GitToolNotFoundError("git not found on PATH")
            result = runner.invoke(app, ["analyze-repo"])

        assert result.exit_code == 1
        assert "git not found on PATH" in result.output
        assert "Traceback" not in result.output


class TestValidateCommand:
    """Tests for the validate command."""

    def test_prints_rho_per_repo(self):
        with patch("black_box_unlock.validation.validate_repo") as mock_validate:
            mock_validate.return_value = _validation_result()
            result = runner.invoke(app, ["validate", "--repo", "."])
        assert result.exit_code == 0
        assert "0.62" in result.stdout

    def test_insufficient_data_prints_counts_not_percentages(self):
        with patch("black_box_unlock.validation.validate_repo") as mock_validate:
            mock_validate.return_value = _validation_result(insufficient=True)
            result = runner.invoke(app, ["validate", "--repo", "."])
        assert "insufficient data: 5 universe files < 20" in result.stdout
        assert "0.62" not in result.stdout
        assert "45%" not in result.stdout
        assert "coverage" not in result.stdout

    def test_all_repos_insufficient_exits_nonzero(self):
        with patch("black_box_unlock.validation.validate_repo") as mock_validate:
            mock_validate.return_value = _validation_result(insufficient=True)
            result = runner.invoke(app, ["validate", "--repo", "."])
        assert result.exit_code == 1
        assert "no repo met the sample floor" in result.stdout

    def test_p_at_the_permutation_floor_prints_as_a_bound(self):
        # zero of 200 draws reached the share: (0 + 1) / 201 is a ceiling, not a measurement
        report = _validation_result().model_copy(update={"p_value": 1 / 201})
        with patch("black_box_unlock.validation.validate_repo") as mock_validate:
            mock_validate.return_value = report
            result = runner.invoke(app, ["validate", "--repo", "."])
        assert "p<0.005 (no draw reached it)" in result.stdout

    def test_report_lines_are_not_wrapped_at_80_columns(self):
        with patch("black_box_unlock.validation.validate_repo") as mock_validate:
            mock_validate.return_value = _validation_result()
            result = runner.invoke(app, ["validate", "--repo", "."])
        assert "90 bug-fix commits after the cutoff, 200 touches on the universe" in result.stdout

    def test_json_output(self):
        with patch("black_box_unlock.validation.validate_repo") as mock_validate:
            mock_validate.return_value = _validation_result()
            result = runner.invoke(app, ["validate", "--repo", ".", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed[0]["methods"]["hotspot"]["spearman"] == 0.62

    def test_median_rho_for_multiple_repos(self):
        results = [
            _validation_result("a", 0.4),
            _validation_result("b", 0.6),
            _validation_result("c", 0.8),
        ]
        with patch("black_box_unlock.validation.validate_repo") as mock_validate:
            mock_validate.side_effect = results
            result = runner.invoke(app, ["validate", "--repo", "a", "--repo", "b", "--repo", "c"])
        assert result.exit_code == 0
        assert "median" in result.stdout.lower()
        assert "0.60" in result.stdout

    def test_median_rho_skips_insufficient_repos(self):
        results = [
            _validation_result("a", 0.4, insufficient=True),
            _validation_result("b", 0.6),
            _validation_result("c", 0.8),
        ]
        with patch("black_box_unlock.validation.validate_repo") as mock_validate:
            mock_validate.side_effect = results
            result = runner.invoke(app, ["validate", "--repo", "a", "--repo", "b", "--repo", "c"])
        assert result.exit_code == 0
        assert "median rho=0.70 across 2 repos" in result.stdout

    def test_failing_repo_reports_error_but_others_continue(self):
        with patch("black_box_unlock.validation.validate_repo") as mock_validate:
            mock_validate.side_effect = [
                InsufficientHistoryError("too little history"),
                _validation_result(),
            ]
            result = runner.invoke(app, ["validate", "--repo", "bad", "--repo", "good"])
        assert result.exit_code == 0
        assert "too little history" in result.stdout

    def test_all_repos_failing_exits_nonzero(self):
        with patch("black_box_unlock.validation.validate_repo") as mock_validate:
            mock_validate.side_effect = InsufficientHistoryError("too little history")
            result = runner.invoke(app, ["validate", "--repo", "bad"])
        assert result.exit_code == 1


def _xray_result():
    from black_box_unlock.core.models import FileXRay, FunctionChurn

    return FileXRay(
        path="mod.py",
        days=365,
        revisions_analyzed=4,
        revision_cap_hit=False,
        functions=[
            FunctionChurn(
                name="alpha",
                start_line=1,
                end_line=3,
                revisions=3,
                lines_added=6,
                lines_deleted=2,
                complexity=2.0,
            )
        ],
    )


class TestXrayCommand:
    def test_outputs_json(self):
        with patch("black_box_unlock.git.xray.xray_file") as mock_xray:
            mock_xray.return_value = _xray_result()
            result = runner.invoke(app, ["xray", "mod.py"])
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["functions"][0]["name"] == "alpha"
        assert parsed["functions"][0]["hotspot_score"] == 6.0

    def test_error_exits_nonzero(self):
        from black_box_unlock.core.exceptions import NotAGitRepoError

        with patch("black_box_unlock.git.xray.xray_file") as mock_xray:
            mock_xray.side_effect = NotAGitRepoError("not a repo")
            result = runner.invoke(app, ["xray", "mod.py"])
        assert result.exit_code == 1
        assert "not a repo" in result.output

    def test_passes_options(self):
        with patch("black_box_unlock.git.xray.xray_file") as mock_xray:
            mock_xray.return_value = _xray_result()
            result = runner.invoke(
                app, ["xray", "mod.py", "--days", "90", "--cap", "50", "--repo", "."]
            )
        assert result.exit_code == 0
        kwargs = mock_xray.call_args[1]
        assert kwargs["days"] == 90 and kwargs["rev_cap"] == 50


class TestAnalyzeRepoXrayTop:
    def test_xray_top_forwarded(self):
        mock_result = MagicMock()
        mock_result.files = []
        with patch("black_box_unlock.cli.run_analysis") as mock_run:
            mock_run.return_value = mock_result
            with patch("black_box_unlock.cli.export_to_json") as mock_export:
                mock_export.return_value = "{}"
                result = runner.invoke(app, ["analyze-repo", "--xray-top", "3"])
        assert result.exit_code == 0
        assert mock_run.call_args[1]["xray_top"] == 3


class TestAnalyzeRepoJsonIntegrity:
    def test_long_json_lines_not_wrapped(self):
        # Rich console.print wraps at terminal width, corrupting JSON strings
        # longer than 80 chars (e.g. qualified function names from X-Ray)
        long_line = '{"name": "' + "x" * 200 + '"}'
        mock_result = MagicMock()
        mock_result.files = []
        with patch("black_box_unlock.cli.run_analysis") as mock_run:
            mock_run.return_value = mock_result
            with patch("black_box_unlock.cli.export_to_json") as mock_export:
                mock_export.return_value = long_line
                result = runner.invoke(app, ["analyze-repo", "--output", "json"])
        assert result.exit_code == 0
        assert long_line in result.stdout


class TestCouplingGuardCommand:
    def test_unexpected_error_is_logged_and_exits_zero(self):
        """A failure in the guard degrades to silence but leaves a diagnosable log line."""
        from loguru import logger

        messages: list[str] = []
        sink = logger.add(messages.append, level="WARNING")
        try:
            # no-op configure_logging so the CLI callback doesn't drop the test sink
            with (
                patch("black_box_unlock.cli.configure_logging"),
                patch(
                    "black_box_unlock.guard.coupling_warnings",
                    side_effect=RuntimeError("boom"),
                ),
            ):
                result = runner.invoke(app, ["coupling-guard", "src/a.py"])
        finally:
            logger.remove(sink)

        assert result.exit_code == 0
        assert any("src/a.py" in m for m in messages)


class TestReviewChangeCommand:
    def test_base_mode_outputs_typed_json(self):
        with patch("black_box_unlock.cli.run_change_review") as mock_review:
            mock_review.return_value.model_dump.return_value = {
                "kind": "no_changes",
                "repo": "demo",
            }
            result = runner.invoke(app, ["review-change", "--base", "origin/main"])

        assert result.exit_code == 0
        assert json.loads(result.stdout)["kind"] == "no_changes"
        request = mock_review.call_args.args[1]
        assert request.selector.kind == "base"
        assert request.selector.base_ref == "origin/main"

    def test_source_flags_are_mutually_exclusive(self):
        result = runner.invoke(
            app,
            ["review-change", "--base", "origin/main", "--staged"],
        )

        assert result.exit_code == 2

    def test_profile_and_overrides_reach_the_review_core(self, tmp_path):
        (tmp_path / ".bbu.toml").write_text(
            """
[[path_roles]]
pattern = "app/**/*.vue"
role = "source"

[profiles.release]
days = 180
include_ci = true
""".strip()
            + "\n"
        )
        with (
            patch("black_box_unlock.cli.run_change_review") as mock_review,
            patch("black_box_unlock.cli.is_shallow", return_value=False),
        ):
            mock_review.return_value.model_dump.return_value = {"kind": "no_changes"}
            result = runner.invoke(
                app,
                [
                    "review-change",
                    "--repo",
                    str(tmp_path),
                    "--profile",
                    "release",
                    "--days",
                    "30",
                ],
            )

        assert result.exit_code == 0
        request = mock_review.call_args.args[1]
        assert request.profile == "release"
        assert request.days == 30
        assert request.include_ci is None

    def test_invalid_config_is_a_clean_cli_error(self, tmp_path):
        (tmp_path / ".bbu.toml").write_text("[profiles.release\n")

        result = runner.invoke(
            app,
            ["review-change", "--repo", str(tmp_path)],
        )

        assert result.exit_code == 1
        assert "Invalid .bbu.toml" in result.stdout
        assert "Traceback" not in result.stdout


@pytest.mark.parametrize(("omitted", "announced"), [(1, True), (0, False)])
def test_review_change_announces_omitted_actions_on_stderr(tmp_path, omitted, announced):
    when = datetime(2026, 7, 30, tzinfo=timezone.utc)
    review = ChangeReview(
        repo="demo",
        generated_at=when,
        provenance=WorkingTreeProvenance(head_oid="abc123", analysed_at=when),
        parameters=ReviewParameters(max_actions=3),
        files=[],
        couplings=[],
        actions=[],
        omitted_actions=omitted,
        ci_status=SignalStatus(),
    )

    with (
        patch("black_box_unlock.cli.run_change_review", return_value=review),
        patch("black_box_unlock.cli.is_shallow", return_value=False),
    ):
        result = runner.invoke(app, ["review-change", "--repo", str(tmp_path)])

    assert result.exit_code == 0, result.stderr
    assert ("1 more action(s) omitted (max_actions=3)" in result.stderr) is announced


def _git(repo, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _coupled_repo(repo: Path) -> Path:
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")
    for revision in ("1", "2"):
        (repo / "a.py").write_text(revision)
        (repo / "b.py").write_text(revision)
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", f"change {revision}")
    return repo


def _hook_payload(path: Path) -> str:
    return json.dumps({"tool_input": {"file_path": str(path)}})


class TestCouplingGuardHookCommand:
    def test_reads_claude_payload_without_jq(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init")
        edited = repo / "src" / "a.py"
        edited.parent.mkdir()
        edited.write_text("x = 1\n")
        payload = json.dumps({"tool_input": {"file_path": str(edited)}})

        with patch("black_box_unlock.guard.coupling_warnings") as mock_warnings:
            mock_warnings.return_value = ["check the companion"]
            result = runner.invoke(
                app,
                ["coupling-guard-hook", "--repo", str(repo)],
                input=payload,
            )

        assert result.exit_code == 0
        assert json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        mock_warnings.assert_called_once_with("src/a.py", repo.resolve())

    def test_subdirectory_resolves_the_repository_root(self, tmp_path):
        repo = _coupled_repo(tmp_path / "repo")
        (repo / "sub").mkdir()

        result = runner.invoke(
            app,
            ["coupling-guard-hook", "--repo", str(repo / "sub")],
            input=_hook_payload(repo / "a.py"),
        )

        assert result.exit_code == 0
        assert "b.py" in json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]

    def test_unexpected_error_exits_zero_and_appends_to_the_hook_log(self, tmp_path):
        repo = _coupled_repo(tmp_path / "repo")

        with patch(
            "black_box_unlock.guard.coupling_warnings",
            side_effect=[RuntimeError("first boom"), RuntimeError("second boom")],
        ):
            results = [
                runner.invoke(
                    app,
                    ["coupling-guard-hook", "--repo", str(repo)],
                    input=_hook_payload(repo / "a.py"),
                )
                for _ in range(2)
            ]

        assert [result.exit_code for result in results] == [0, 0]
        lines = (repo / ".git" / "bbu" / "hook.log").read_text().splitlines()
        assert len(lines) == 2
        assert "RuntimeError: first boom" in lines[0]
        assert "RuntimeError: second boom" in lines[1]

    def test_hook_declaration_keeps_stderr_visible(self, repo_root):
        hooks = json.loads((repo_root / "hooks" / "hooks.json").read_text())
        command = hooks["hooks"]["PostToolUse"][0]["hooks"][0]["command"]

        assert "2>/dev/null" not in command
        assert command.endswith("|| true")

    def test_hooks_declaration_has_no_jq_dependency(self, repo_root):
        hooks = (repo_root / "hooks" / "hooks.json").read_text()

        assert "jq" not in hooks
        assert "coupling-guard-hook" in hooks


class TestDoctorCommand:
    def test_reports_the_hook_log_and_its_last_line(self, tmp_path):
        repo = _coupled_repo(tmp_path / "repo")
        log = repo / ".git" / "bbu" / "hook.log"
        log.parent.mkdir()
        log.write_text("t1 RuntimeError: old\nt2 RuntimeError: newest\n")

        result = runner.invoke(app, ["doctor", "--repo", str(repo)])

        hook_log = json.loads(result.stdout)["hook_log"]
        assert hook_log["path"] == str(log.resolve())
        assert hook_log["last_line"] == "t2 RuntimeError: newest"

    def test_invalid_config_makes_doctor_fail_honestly(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".bbu.toml").write_text("surprise = true\n")

        result = runner.invoke(app, ["doctor", "--repo", str(tmp_path)])

        parsed = json.loads(result.stdout)
        assert parsed["ok"] is False
        assert parsed["checks"]["config"] is False
        assert "surprise" in parsed["config"]["error"]


class TestXrayMinCoupling:
    def test_min_coupling_forwarded(self):
        with patch("black_box_unlock.git.xray.xray_file") as mock_xray:
            mock_xray.return_value = _xray_result()
            result = runner.invoke(app, ["xray", "mod.py", "--min-coupling", "0.5"])
        assert result.exit_code == 0
        assert mock_xray.call_args[1]["min_coupling"] == 0.5


class TestOptionBounds:
    @pytest.mark.parametrize(
        "args",
        [
            ["analyze-repo", "--min-coupling", "1.5"],
            ["analyze-repo", "--min-coupling", "-1"],
            ["review-change", "--min-coupling", "1.5"],
            ["review-change", "--min-shared-revisions", "0"],
            ["xray", "mod.py", "--min-coupling", "1.5"],
        ],
    )
    def test_out_of_range_values_are_rejected_before_analysis(self, args):
        with (
            patch("black_box_unlock.cli.run_analysis") as mock_analysis,
            patch("black_box_unlock.cli.run_change_review") as mock_review,
            patch("black_box_unlock.git.xray.xray_file") as mock_xray,
        ):
            result = runner.invoke(app, args)

        assert result.exit_code == 2
        assert "Invalid value" in result.output
        mock_analysis.assert_not_called()
        mock_review.assert_not_called()
        mock_xray.assert_not_called()


class TestCouplingGuardHookOutsideRepo:
    def test_edit_outside_the_repository_is_not_a_failure(self, tmp_path):
        repo = _coupled_repo(tmp_path / "repo")
        outside = tmp_path / "outside.py"
        outside.write_text("x = 1\n")

        result = runner.invoke(
            app, ["coupling-guard-hook", "--repo", str(repo)], input=_hook_payload(outside)
        )

        assert result.exit_code == 0
        assert result.stdout == ""
        assert not (repo / ".git" / "bbu" / "hook.log").exists()
