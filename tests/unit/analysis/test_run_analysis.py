"""Unit tests for run_analysis and the coupling policy inside the pipeline."""

from pathlib import Path
from unittest.mock import patch

import pytest

from black_box_unlock.analysis import run_analysis
from black_box_unlock.core.models import (
    AnalysisResult,
    CouplingPolicy,
)
from tests.factories import make_commit


class TestRunAnalysis:
    """Tests for run_analysis function."""

    def test_returns_analysis_result_with_file_data(self):
        """Returns AnalysisResult with forensics from git history."""
        history = [
            make_commit(
                author_email="alice@example.com",
                files=[
                    {"path": "src/auth.py", "added_lines": 100, "deleted_lines": 20},
                    {"path": "src/user.py", "added_lines": 50, "deleted_lines": 10},
                ],
            ),
            make_commit(
                author_email="bob@example.com",
                files=[{"path": "src/auth.py", "added_lines": 30, "deleted_lines": 5}],
            ),
        ]

        with patch("black_box_unlock.git.history.fetch_git_history") as mock_fetch:
            mock_fetch.return_value = history
            result = run_analysis(Path("/fake/repo"), days=30)

        assert isinstance(result, AnalysisResult)
        assert result.analyzed_days == 30
        assert len(result.files) == 2

        # Check auth.py forensics
        auth_file = next(f for f in result.files if f.path == "src/auth.py")
        assert auth_file.commits == 2
        assert auth_file.lines_changed == 155  # 100+20+30+5
        assert auth_file.author_count == 2
        assert set(auth_file.authors) == {"alice@example.com", "bob@example.com"}

    def test_copies_main_author_share_and_last_active_onto_forensics(self):
        history = [
            make_commit(
                ["a.py"], author_email="alice@example.com", timestamp="2026-01-01T00:00:00+00:00"
            ),
            make_commit(
                ["a.py"], author_email="alice@example.com", timestamp="2026-01-02T00:00:00+00:00"
            ),
            make_commit(
                ["a.py"], author_email="bob@example.com", timestamp="2026-01-05T00:00:00+00:00"
            ),
        ]

        with patch("black_box_unlock.git.history.fetch_git_history") as mock_fetch:
            mock_fetch.return_value = history
            result = run_analysis(Path("/fake/repo"), days=30)

        (forensics,) = result.files
        assert forensics.main_author == "alice@example.com"
        assert forensics.main_author_share == pytest.approx(2 / 3)
        assert forensics.last_active.day == 5
        dumped = forensics.model_dump(mode="json")
        assert dumped["main_author"] == "alice@example.com"
        assert dumped["last_active"].startswith("2026-01-05")

    def test_computes_hotspot_scores(self):
        """Files are sorted by hotspot_score descending."""
        history = [make_commit(["low.py", "high.py"], author_email="alice@example.com")]
        complexity_by_path = {"low.py": 1.0, "high.py": 50.0}

        with patch("black_box_unlock.git.history.fetch_git_history") as mock_fetch:
            mock_fetch.return_value = history
            with patch("black_box_unlock.analysis.indentation_complexity") as mock_cx:
                mock_cx.side_effect = lambda p: complexity_by_path.get(p.name, 0.0)
                result = run_analysis(Path("/fake/repo"), days=30)

        assert result.files[0].path == "high.py"
        assert result.files[1].path == "low.py"

    def test_includes_coupling_info(self, head_tree):
        """Files include coupling info when above threshold."""
        head_tree.return_value = frozenset({"a.py", "b.py"})
        history = [
            make_commit(["a.py", "b.py"], author_email="alice@example.com"),
            make_commit(["a.py", "b.py"], author_email="alice@example.com"),
        ]

        with patch("black_box_unlock.git.history.fetch_git_history") as mock_fetch:
            mock_fetch.return_value = history
            result = run_analysis(Path("/fake/repo"), days=30)

        # a.py and b.py have 100% coupling (2/2 commits together)
        a_file = next(f for f in result.files if f.path == "a.py")
        assert len(a_file.coupled_with) == 1
        assert a_file.coupled_with[0].file == "b.py"
        assert a_file.coupled_with[0].ratio == 1.0
        assert a_file.coupled_with[0].shared_revisions == 2
        assert a_file.coupled_with[0].file_revisions == 2
        assert a_file.coupled_with[0].coupled_file_revisions == 2
        assert a_file.coupled_with[0].rate_lower_bound > 0
        assert result.couplings[0].co_change_count == 2

    def test_caller_renames_reach_history_as_aliases_and_surface_in_renamed_from(self):
        """The reviewed change's own renames seed git history, so the final path carries every former name."""
        history = [
            make_commit(files=[{"path": "src/c.py", "former_paths": ["src/b.py"]}]),
            make_commit(files=[{"path": "src/c.py", "former_paths": ["src/a.py", "src/b.py"]}]),
            make_commit(["src/other.py"]),
        ]
        with patch("black_box_unlock.git.history.fetch_git_history", return_value=history) as fetch:
            result = run_analysis(
                Path("/fake/repo"),
                include_ci=False,
                xray_top=0,
                path_aliases={"src/b.py": "src/c.py"},
            )

        fetch.assert_called_once_with(
            Path("/fake/repo"), 30, None, aliases={"src/b.py": "src/c.py"}
        )
        by_path = {file.path: file for file in result.files}
        assert set(by_path) == {"src/c.py", "src/other.py"}
        assert by_path["src/c.py"].commits == 2
        assert by_path["src/c.py"].renamed_from == ["src/a.py", "src/b.py"]
        assert by_path["src/other.py"].renamed_from == []

    def test_result_carries_the_provenance_of_the_state_it_read(self):
        history = [make_commit(["a.py"])]
        with patch("black_box_unlock.git.history.fetch_git_history", return_value=history):
            result = run_analysis(Path("/fake/repo"), days=30, include_ci=False, xray_top=0)

        assert result.provenance.head_oid == "a" * 40
        assert result.provenance.days == 30
        assert result.provenance.include_ci is False
        assert result.provenance.cached is False
        assert result.provenance.analysed_at == result.generated_at

    def test_ensure_paths_includes_a_current_file_without_history(self):
        with (
            patch("black_box_unlock.git.history.fetch_git_history", return_value=[]),
            patch("black_box_unlock.analysis.indentation_complexity", return_value=7.0),
        ):
            result = run_analysis(
                Path("/fake/repo"),
                include_ci=False,
                xray_top=0,
                ensure_paths=frozenset({"src/new.py"}),
            )

        assert len(result.files) == 1
        assert result.files[0].path == "src/new.py"
        assert result.files[0].commits == 0
        assert result.files[0].complexity == 7.0

    def test_summary_counts_high_risk_files(self):
        """Summary counts files with >3 authors as high risk."""
        history = [
            make_commit(["risky.py"], author_email="a@x.com"),
            make_commit(["risky.py"], author_email="b@x.com"),
            make_commit(["risky.py"], author_email="c@x.com"),
            make_commit(["risky.py"], author_email="d@x.com"),
            make_commit(["safe.py"], author_email="a@x.com"),
        ]

        with patch("black_box_unlock.git.history.fetch_git_history") as mock_fetch:
            mock_fetch.return_value = history
            result = run_analysis(Path("/fake/repo"), days=30)

        assert result.summary.high_risk_ownership == 1
        assert result.summary.total_files == 2

    def test_equal_hotspot_scores_ordered_by_path(self):
        """Files with tied hotspot scores sort by path, so output is reproducible."""
        names = ["m.py", "b.py", "z.py", "a.py", "k.py", "f.py"]
        history = [make_commit(names)]  # each file: one commit, equal complexity -> tied score
        with patch("black_box_unlock.git.history.fetch_git_history") as mock_fetch:
            mock_fetch.return_value = history
            with patch("black_box_unlock.analysis.indentation_complexity") as mock_cx:
                mock_cx.return_value = 3.0
                result = run_analysis(Path("/fake/repo"), days=30, include_ci=False, xray_top=0)

        assert [f.path for f in result.files] == sorted(names)

    def test_records_parameters_and_ignored_bulk_changesets(self):
        history = [make_commit([f"generated/{i}.py" for i in range(51)])]
        with patch("black_box_unlock.git.history.fetch_git_history", return_value=history):
            result = run_analysis(
                Path("/fake/repo"),
                days=45,
                include_ci=False,
                xray_top=0,
                policy=CouplingPolicy(min_ratio=0.75),
            )

        assert result.parameters.model_dump() == {
            "coupling": {
                "min_ratio": 0.75,
                "min_shared_revisions": 2,
                "max_changeset_size": 50,
                "require_live_partner": True,
            },
            "include_ci": False,
            "xray_top": 0,
        }
        assert result.summary.ignored_large_changesets == 1

    def test_policy_defaults_come_from_bbu_toml(self, tmp_path):
        (tmp_path / ".bbu.toml").write_text("[coupling]\nmin_shared_revisions = 4\n")
        with patch("black_box_unlock.git.history.fetch_git_history", return_value=[]):
            result = run_analysis(tmp_path, include_ci=False, xray_top=0)

        assert result.parameters.coupling == CouplingPolicy(min_shared_revisions=4)


class TestCouplingPolicyInPipeline:
    def test_bulk_commit_is_excluded_from_every_history_signal(self, head_tree):
        head_tree.return_value = frozenset({"src/a.py", "src/b.py"})
        bulk = make_commit(
            ["src/a.py", "src/b.py", *[f"gen/{i}.py" for i in range(49)]],
            author_email="bot@example.com",
            message="fix: reformat everything",
        )
        history = [
            bulk,
            make_commit(["src/a.py", "src/b.py"], author_email="dev@example.com"),
            make_commit(["src/a.py", "src/b.py"], author_email="dev@example.com"),
        ]

        with patch("black_box_unlock.git.history.fetch_git_history", return_value=history):
            result = run_analysis(Path("/fake/repo"), include_ci=False, xray_top=0)

        a = next(file for file in result.files if file.path == "src/a.py")
        assert (a.commits, a.bugfix_commits, a.authors) == (2, 0, ["dev@example.com"])
        assert result.couplings[0].commits_a == 2
        assert not any(file.path.startswith("gen/") for file in result.files)
        assert result.summary.ignored_large_changesets == 1

    def test_single_observation_pairs_are_not_reported(self, head_tree):
        head_tree.return_value = frozenset({"a.py", "b.py"})
        history = [make_commit(["a.py", "b.py"])]

        with patch("black_box_unlock.git.history.fetch_git_history", return_value=history):
            result = run_analysis(Path("/fake/repo"), include_ci=False, xray_top=0)

        assert result.couplings == []
        assert result.summary.coupled_pairs == 0

    def test_partner_deleted_at_head_is_dropped_and_counted(self, head_tree):
        head_tree.return_value = frozenset({"src/a.py"})
        history = [make_commit(["src/a.py", "src/gone.py"]) for _ in range(3)]

        with patch("black_box_unlock.git.history.fetch_git_history", return_value=history):
            result = run_analysis(Path("/fake/repo"), include_ci=False, xray_top=0)

        a = next(file for file in result.files if file.path == "src/a.py")
        assert a.coupled_with == []
        assert result.couplings == []
        assert result.summary.dropped_deleted_partners == 1

    def test_deleted_partner_is_kept_when_live_partner_is_not_required(self, head_tree):
        history = [make_commit(["src/a.py", "src/gone.py"]) for _ in range(3)]

        with patch("black_box_unlock.git.history.fetch_git_history", return_value=history):
            result = run_analysis(
                Path("/fake/repo"),
                include_ci=False,
                xray_top=0,
                policy=CouplingPolicy(require_live_partner=False),
            )

        head_tree.assert_not_called()
        assert [(pair.file_a, pair.file_b) for pair in result.couplings] == [
            ("src/a.py", "src/gone.py")
        ]

    def test_ensured_path_counts_as_live(self, head_tree):
        history = [make_commit(["src/new_name.py", "src/b.py"]) for _ in range(2)]
        head_tree.return_value = frozenset({"src/b.py"})

        with patch("black_box_unlock.git.history.fetch_git_history", return_value=history):
            result = run_analysis(
                Path("/fake/repo"),
                include_ci=False,
                xray_top=0,
                ensure_paths=frozenset({"src/new_name.py"}),
            )

        assert len(result.couplings) == 1

    def test_hub_does_not_list_a_leaf_but_the_leaf_lists_the_hub(self, head_tree):
        head_tree.return_value = frozenset({"hub.py", "leaf.py"})
        history = [
            *[make_commit(["hub.py", "leaf.py"]) for _ in range(3)],
            *[make_commit(["hub.py"]) for _ in range(27)],
        ]

        with patch("black_box_unlock.git.history.fetch_git_history", return_value=history):
            result = run_analysis(Path("/fake/repo"), include_ci=False, xray_top=0)

        by_path = {file.path: file for file in result.files}
        assert by_path["hub.py"].coupled_with == []
        assert [info.file for info in by_path["leaf.py"].coupled_with] == ["hub.py"]
        assert by_path["leaf.py"].coupled_with[0].rate_to_partner == 1.0
        pair = result.couplings[0]
        assert (pair.rate_a_to_b, pair.rate_b_to_a, pair.coupling_ratio) == (0.1, 1.0, 1.0)
