"""Unit tests for the bbu-mcp server tools."""

import asyncio
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

from black_box_unlock import mcp_server
from black_box_unlock.core.exceptions import NotAGitRepoError
from black_box_unlock.core.models import (
    AnalysisResult,
    AnalysisSummary,
    CouplingInfo,
    FailedWorkflowRun,
    FileForensics,
    Provenance,
    SignalState,
    SignalStatus,
)


def _result() -> AnalysisResult:
    return AnalysisResult(
        repo="demo",
        analyzed_days=30,
        generated_at=datetime(2026, 6, 12),
        files=[
            FileForensics(
                path="src/auth.py",
                commits=10,
                lines_changed=500,
                complexity=40.0,
                authors=["a@x.com"],
                coupled_with=[
                    CouplingInfo(
                        file="src/token.py",
                        ratio=0.8,
                        shared_revisions=8,
                        file_revisions=10,
                        coupled_file_revisions=10,
                        confidence_lower_bound=0.49,
                    )
                ],
                build_failures=2,
                bugfix_commits=3,
            ),
            FileForensics(
                path="src/util.py",
                commits=2,
                lines_changed=20,
                complexity=5.0,
                authors=["a@x.com"],
                coupled_with=[],
            ),
        ],
        summary=AnalysisSummary(total_files=2, high_risk_ownership=0, coupled_pairs=1),
        ci_status=SignalStatus(state=SignalState.available),
        provenance=Provenance(
            head_oid="a" * 40,
            analysed_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
            days=30,
            include_ci=False,
            shallow_clone=False,
            bbu_version="1.5.2",
        ),
    )


@patch("black_box_unlock.mcp_server._analysis")
class TestMcpTools:
    def test_get_hotspots_returns_top_n_sorted(self, mock_analysis):
        mock_analysis.return_value = _result()

        out = mcp_server.get_hotspots(repo_path=".", days=30, top_n=1)
        hotspots = out["hotspots"]

        assert len(hotspots) == 1
        assert hotspots[0]["path"] == "src/auth.py"
        assert hotspots[0]["hotspot_score"] == 400.0
        assert hotspots[0]["bugfix_commits"] == 3

    def test_get_hotspots_roles_filter_runs_before_top_n(self, mock_analysis):
        result = _result()
        result.files.insert(
            0,
            FileForensics(
                path="tests/test_auth.py",
                commits=20,
                lines_changed=900,
                complexity=50.0,
                authors=["a@x.com"],
                coupled_with=[],
            ),
        )
        mock_analysis.return_value = result

        source = mcp_server.get_hotspots(repo_path=".", top_n=1, roles=["source"])["hotspots"]
        tests = mcp_server.get_hotspots(repo_path=".", roles=["test"])["hotspots"]
        both = mcp_server.get_hotspots(repo_path=".", roles=["test", "source"])["hotspots"]
        unfiltered = mcp_server.get_hotspots(repo_path=".")["hotspots"]

        assert [f["path"] for f in source] == ["src/auth.py"]
        assert [f["path"] for f in tests] == ["tests/test_auth.py"]
        assert tests[0]["path_role"] == "test"
        assert len(both) == len(unfiltered) == 3

    def test_get_hotspots_unknown_role_raises(self, mock_analysis):
        mock_analysis.return_value = _result()

        with pytest.raises(ToolError, match="Unknown path role"):
            mcp_server.get_hotspots(repo_path=".", roles=["source", "scrips"])

    def test_get_hotspots_empty_roles_raises(self, mock_analysis):
        mock_analysis.return_value = _result()

        with pytest.raises(ToolError, match="roles must not be empty"):
            mcp_server.get_hotspots(repo_path=".", roles=[])

    def test_get_file_forensics_finds_file(self, mock_analysis):
        mock_analysis.return_value = _result()

        info = mcp_server.get_file_forensics("src/auth.py", repo_path=".", days=30)

        assert info["commits"] == 10
        assert info["build_failures"] == 2

    def test_get_file_forensics_unknown_file_raises(self, mock_analysis):
        mock_analysis.return_value = _result()

        with pytest.raises(ToolError, match="nope.py is not in the repository tree"):
            mcp_server.get_file_forensics("nope.py", repo_path=".", days=30)

    def test_get_coupled_files(self, mock_analysis):
        mock_analysis.return_value = _result()

        coupled = mcp_server.get_coupled_files("src/auth.py", repo_path=".", days=30)

        assert coupled["coupled_files"] == [
            {
                "file": "src/token.py",
                "ratio": 0.8,
                "shared_revisions": 8,
                "file_revisions": 10,
                "coupled_file_revisions": 10,
                "confidence_lower_bound": 0.49,
                "rate_to_partner": 0.8,
            }
        ]

    def test_get_ci_failures_only_nonzero(self, mock_analysis):
        mock_analysis.return_value = _result()

        failures = mcp_server.get_ci_failures(repo_path=".")

        assert failures.pop("provenance")["head_oid"] == "a" * 40
        assert failures == {
            "status": "available",
            "errors": [],
            "files": [{"path": "src/auth.py", "build_failures": 2}],
            "runs": [],
        }

    def test_get_ci_failures_keeps_actionable_run_details(self, mock_analysis):
        result = _result()
        result.failed_ci_runs = [
            FailedWorkflowRun(
                run_id=42,
                workflow_name="CI",
                run_url="https://github.com/example/repo/actions/runs/42",
                commit_sha="abc123",
                conclusion="failure",
                created_at=datetime(2026, 6, 12),
                implicated_paths=["src/auth.py"],
            )
        ]
        mock_analysis.return_value = result

        failures = mcp_server.get_ci_failures(repo_path=".")

        assert failures["runs"][0] == {
            "run_id": 42,
            "workflow_name": "CI",
            "run_url": "https://github.com/example/repo/actions/runs/42",
            "commit_sha": "abc123",
            "conclusion": "failure",
            "created_at": "2026-06-12T00:00:00",
            "implicated_paths": ["src/auth.py"],
            "attribution": "changed_in_failed_commit",
        }

    def test_get_flaky_steps_reports_signal_status(self, mock_analysis):
        mock_analysis.return_value = _result()

        flaky = mcp_server.get_flaky_steps(repo_path=".")

        assert flaky.pop("provenance")["head_oid"] == "a" * 40
        assert flaky == {
            "status": "available",
            "errors": [],
            "steps": [],
        }

    def test_get_ownership_reports_share_recency_and_risk(self, mock_analysis):
        result = _result()
        result.files[0] = result.files[0].model_copy(
            update={
                "authors": ["a@x.com", "b@x.com", "c@x.com", "d@x.com"],
                "main_author": "a@x.com",
                "main_author_share": 0.25,
                "last_active": datetime(2026, 6, 1, tzinfo=timezone.utc),
            }
        )
        mock_analysis.return_value = result

        info = mcp_server.get_ownership("src/auth.py", repo_path=".", days=30)

        assert info["main_author"] == "a@x.com"
        assert info["main_author_share"] == 0.25
        assert info["last_active"] == "2026-06-01T00:00:00+00:00"
        assert info["ownership_risk"] == "diffuse"

    def test_get_ownership_without_history_has_null_owner_and_owned_risk(self, mock_analysis):
        mock_analysis.return_value = _result()

        info = mcp_server.get_ownership("src/util.py", repo_path=".", days=30)

        assert info["main_author"] is None
        assert info["main_author_share"] == 0.0
        assert info["last_active"] is None
        assert info["ownership_risk"] == "owned"

    def test_get_ownership_unknown_file_raises(self, mock_analysis):
        mock_analysis.return_value = _result()

        with pytest.raises(ToolError, match="nope.py is not in the repository tree"):
            mcp_server.get_ownership("nope.py", repo_path=".", days=30)

    def test_bad_repo_raises_tool_error(self, mock_analysis):
        mock_analysis.side_effect = NotAGitRepoError("Not a git repository: /tmp")

        with pytest.raises(ToolError, match="Not a git repository: /tmp"):
            mcp_server.get_hotspots(repo_path="/tmp", days=1)


class TestAnalysisCache:
    @patch("black_box_unlock.mcp_server.run_analysis")
    def test_same_args_hit_cache(self, mock_run):
        mock_run.return_value = _result()
        mcp_server._cache.clear()

        mcp_server._analysis(".", 30, False)
        mcp_server._analysis(".", 30, False)

        assert mock_run.call_count == 1

    @patch("black_box_unlock.mcp_server.run_analysis")
    def test_different_include_ci_are_separate_cache_entries(self, mock_run):
        mock_run.return_value = _result()
        mcp_server._cache.clear()

        mcp_server._analysis(".", 30, False)
        mcp_server._analysis(".", 30, True)

        assert mock_run.call_count == 2


class TestToolRegistration:
    def test_all_eight_tools_registered(self):
        names = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
        assert names == {
            "get_hotspots",
            "get_file_forensics",
            "get_coupled_files",
            "get_ownership",
            "get_ci_failures",
            "get_flaky_steps",
            "xray_file",
            "review_change",
        }


class TestErrorsReachTheClient:
    @patch("black_box_unlock.mcp_server._analysis")
    def test_tool_error_message_is_returned_to_the_caller(self, mock_analysis):
        mock_analysis.side_effect = NotAGitRepoError("Not a git repository: /tmp")

        with pytest.raises(ToolError, match="Not a git repository: /tmp") as raised:
            asyncio.run(
                mcp_server.mcp.call_tool("get_hotspots", {"repo_path": "/tmp"}, context=None)
            )

        # UnexpectedToolError is the crash path: the server hides its message from the client.
        assert not isinstance(raised.value, UnexpectedToolError)


class TestReviewChangeTool:
    def test_review_is_fresh_and_bypasses_analysis_cache(self):
        with patch("black_box_unlock.mcp_server._run_change_review") as mock_review:
            mock_review.return_value.model_dump.return_value = {"kind": "no_changes"}

            mcp_server.review_change(repo_path=".", mode="working_tree")
            mcp_server.review_change(repo_path=".", mode="working_tree")

        assert mock_review.call_count == 2

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
        with patch("black_box_unlock.mcp_server._run_change_review") as mock_review:
            mock_review.return_value.model_dump.return_value = {"kind": "no_changes"}

            mcp_server.review_change(
                repo_path=str(tmp_path),
                profile="release",
                days=30,
            )

        request = mock_review.call_args.args[1]
        assert request.profile == "release"
        assert request.days == 30
        assert request.include_ci is None


class TestXrayFileTool:
    def test_returns_function_churn_json(self):
        from black_box_unlock.core.models import FileXRay, FunctionChurn

        fake = FileXRay(
            path="mod.py",
            days=365,
            revisions_analyzed=2,
            revision_cap_hit=False,
            functions=[
                FunctionChurn(
                    name="alpha",
                    start_line=1,
                    end_line=3,
                    revisions=2,
                    lines_added=4,
                    lines_deleted=1,
                    complexity=2.0,
                )
            ],
        )
        with patch("black_box_unlock.mcp_server._xray_file") as mock_xray:
            mock_xray.return_value = fake
            out = mcp_server.xray_file("mod.py", repo_path=".", days=365)
        assert out["functions"][0]["hotspot_score"] == 4.0
        assert out["provenance"]["days"] == 365
        assert out["provenance"]["cached"] is False

    def test_unmeasurable_complexity_serializes_as_null_with_reason(self):
        from black_box_unlock.core.models import FileXRay, FunctionChurn

        fake = FileXRay(
            path="gen.py",
            days=365,
            revisions_analyzed=1,
            revision_cap_hit=False,
            functions=[
                FunctionChurn(
                    name="f",
                    revisions=1,
                    lines_added=1,
                    lines_deleted=0,
                    complexity=None,
                    score_unavailable_reason="current snapshot could not be parsed",
                )
            ],
        )
        with patch("black_box_unlock.mcp_server._xray_file", return_value=fake):
            out = mcp_server.xray_file("gen.py")
        fn = out["functions"][0]
        assert fn["hotspot_score"] is None
        assert fn["complexity"] is None
        assert fn["score_unavailable_reason"] == "current snapshot could not be parsed"

    def test_bbu_error_becomes_tool_error(self):
        with patch("black_box_unlock.mcp_server._xray_file") as mock_xray:
            mock_xray.side_effect = NotAGitRepoError("not a repo")
            with pytest.raises(ToolError, match="not a repo"):
                mcp_server.xray_file("mod.py")


class TestXrayFileToolCoupling:
    def test_min_coupling_forwarded_and_coupling_serialized(self):
        from black_box_unlock.core.models import FileXRay, FunctionCoupling

        fake = FileXRay(
            path="mod.py",
            days=365,
            revisions_analyzed=3,
            revision_cap_hit=False,
            functions=[],
            coupling=[
                FunctionCoupling(
                    function_a="alpha",
                    function_b="beta",
                    shared_revisions=2,
                    revisions_a=3,
                    revisions_b=2,
                )
            ],
        )
        with patch("black_box_unlock.mcp_server._xray_file") as mock_xray:
            mock_xray.return_value = fake
            out = mcp_server.xray_file("mod.py", min_coupling=0.5)
        assert mock_xray.call_args[1]["min_coupling"] == 0.5
        assert out["coupling"][0]["coupling_ratio"] == 1.0


def _git(repo: Path, *args: str, date: str | None = None) -> None:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


def _commit(repo: Path, name: str, date: str | None = None) -> None:
    (repo / name).write_text("def f():\n    if True:\n        return 1\n")
    _git(repo, "add", name)
    _git(
        repo,
        "-c",
        "user.name=T",
        "-c",
        "user.email=t@example.com",
        "commit",
        "-m",
        f"add {name}",
        date=date,
    )


@pytest.fixture
def scratch(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _commit(repo, "a.py")
    mcp_server._cache.clear()
    return repo


class TestCacheFollowsRepositoryState:
    def test_new_commit_is_reflected(self, scratch):
        before = mcp_server.get_hotspots(repo_path=str(scratch))
        _commit(scratch, "b.py")

        after = mcp_server.get_hotspots(repo_path=str(scratch))

        assert {h["path"] for h in before["hotspots"]} == {"a.py"}
        assert {h["path"] for h in after["hotspots"]} == {"a.py", "b.py"}
        assert after["provenance"]["head_oid"] != before["provenance"]["head_oid"]

    def test_cached_flag_reports_whether_the_call_hit_the_cache(self, scratch):
        first = mcp_server.get_hotspots(repo_path=str(scratch))
        second = mcp_server.get_hotspots(repo_path=str(scratch))

        assert first["provenance"]["cached"] is False
        assert second["provenance"]["cached"] is True
        assert second["provenance"]["analysed_at"] == first["provenance"]["analysed_at"]

    def test_new_hour_bucket_reruns_the_analysis(self, scratch):
        with patch("black_box_unlock.mcp_server._hour_bucket", side_effect=[1, 1, 2]):
            first = mcp_server.get_hotspots(repo_path=str(scratch))
            second = mcp_server.get_hotspots(repo_path=str(scratch))
            third = mcp_server.get_hotspots(repo_path=str(scratch))

        assert [r["provenance"]["cached"] for r in (first, second, third)] == [False, True, False]

    @patch("black_box_unlock.mcp_server.run_analysis")
    def test_cache_is_bounded(self, mock_run, scratch):
        mock_run.return_value = _result()

        for days in range(1, 13):
            mcp_server._analysis(str(scratch), days)

        assert len(mcp_server._cache) == mcp_server._CACHE_SIZE == 8
        mock_run.reset_mock()
        mcp_server._analysis(str(scratch), 12)
        assert mock_run.call_count == 0
        mcp_server._analysis(str(scratch), 1)
        assert mock_run.call_count == 1


class TestAnalysisRequest:
    @patch("black_box_unlock.mcp_server.run_analysis")
    def test_mcp_skips_auto_xray(self, mock_run, scratch):
        mock_run.return_value = _result()

        mcp_server._analysis(str(scratch), 30)

        assert mock_run.call_args.kwargs["xray_top"] == 0


class TestProvenance:
    def test_every_tool_result_carries_provenance(self, scratch):
        calls = [
            mcp_server.get_hotspots(repo_path=str(scratch)),
            mcp_server.get_file_forensics("a.py", repo_path=str(scratch)),
            mcp_server.get_coupled_files("a.py", repo_path=str(scratch)),
            mcp_server.get_ownership("a.py", repo_path=str(scratch)),
            mcp_server.xray_file("a.py", repo_path=str(scratch)),
        ]
        for out in calls:
            prov = out["provenance"]
            assert set(prov) == {
                "head_oid",
                "analysed_at",
                "days",
                "include_ci",
                "shallow_clone",
                "bbu_version",
                "cached",
            }
            assert len(prov["head_oid"]) == 40
            assert prov["shallow_clone"] is False

    def test_shallow_clone_is_flagged(self, scratch, tmp_path):
        _commit(scratch, "b.py")
        clone = tmp_path / "clone"
        subprocess.run(
            ["git", "clone", "--depth", "1", f"file://{scratch}", str(clone)],
            check=True,
            capture_output=True,
        )

        out = mcp_server.get_hotspots(repo_path=str(clone))

        assert out["provenance"]["shallow_clone"] is True


class TestPathHandling:
    def test_absolute_path_inside_repo_is_normalised(self, scratch):
        rel = mcp_server.get_file_forensics("a.py", repo_path=str(scratch))
        absolute = mcp_server.get_file_forensics(str(scratch / "a.py"), repo_path=str(scratch))

        assert absolute["path"] == rel["path"] == "a.py"

    def test_absolute_path_outside_repo_raises(self, scratch, tmp_path):
        outside = tmp_path / "elsewhere.py"
        outside.write_text("x = 1\n")

        for call in (
            lambda: mcp_server.get_file_forensics(str(outside), repo_path=str(scratch)),
            lambda: mcp_server.get_coupled_files(str(outside), repo_path=str(scratch)),
            lambda: mcp_server.xray_file(str(outside), repo_path=str(scratch)),
        ):
            with pytest.raises(ToolError, match="outside the repository"):
                call()

    def test_dotdot_escape_raises(self, scratch):
        with pytest.raises(ToolError, match="outside the repository"):
            mcp_server.get_ownership("../x.py", repo_path=str(scratch))

    def test_nonexistent_path_is_not_in_tree(self, scratch):
        for call in (
            lambda: mcp_server.get_file_forensics("nope.py", repo_path=str(scratch)),
            lambda: mcp_server.get_coupled_files("nope.py", repo_path=str(scratch)),
            lambda: mcp_server.get_ownership("nope.py", repo_path=str(scratch)),
            lambda: mcp_server.xray_file("nope.py", repo_path=str(scratch)),
        ):
            with pytest.raises(ToolError, match="nope.py is not in the repository tree"):
                call()

    def test_existing_path_without_history_in_window(self, scratch):
        _commit(scratch, "old.py", date="2020-01-01T00:00:00Z")
        mcp_server._cache.clear()

        for call in (
            lambda: mcp_server.get_file_forensics("old.py", repo_path=str(scratch), days=30),
            lambda: mcp_server.get_coupled_files("old.py", repo_path=str(scratch), days=30),
            lambda: mcp_server.xray_file("old.py", repo_path=str(scratch), days=30),
        ):
            with pytest.raises(ToolError, match="old.py exists but has no history in the last 30"):
                call()


class TestUnbornAndUntrackedPaths:
    def test_unborn_repository_returns_no_hotspots(self, tmp_path):
        repo = tmp_path / "fresh"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        mcp_server._cache.clear()

        result = mcp_server.get_hotspots(repo_path=str(repo))

        assert result["hotspots"] == []
        assert result["provenance"]["head_oid"] is None

    def test_gitignored_file_is_not_in_tree(self, scratch):
        (scratch / ".gitignore").write_text("ignored.txt\n")
        (scratch / "ignored.txt").write_text("x\n")
        _git(scratch, "add", ".gitignore")
        _git(
            scratch, "-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-m", "ignore"
        )
        mcp_server._cache.clear()

        with pytest.raises(ToolError, match="not in the repository tree"):
            mcp_server.get_file_forensics("ignored.txt", repo_path=str(scratch))
        with pytest.raises(ToolError, match="not in the repository tree"):
            mcp_server.xray_file("ignored.txt", repo_path=str(scratch))

    def test_directory_path_is_rejected(self, scratch):
        (scratch / "sub").mkdir()
        (scratch / "sub" / "b.py").write_text("y = 1\n")
        _git(scratch, "add", "sub")
        _git(scratch, "-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-m", "sub")
        mcp_server._cache.clear()

        with pytest.raises(ToolError, match="is a directory"):
            mcp_server.get_file_forensics("sub", repo_path=str(scratch))

    def test_tracked_symlink_keeps_its_own_path(self, scratch):
        (scratch / "link.py").symlink_to("a.py")
        _git(scratch, "add", "link.py")
        _git(scratch, "-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-m", "link")
        mcp_server._cache.clear()

        info = mcp_server.get_ownership("link.py", repo_path=str(scratch))

        assert info["path"] == "link.py"
