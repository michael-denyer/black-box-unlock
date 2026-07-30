"""Tests for typed Git change selection."""

from unittest.mock import patch

from black_box_unlock.git.changes import (
    BaseChange,
    ChangeKind,
    StagedChange,
    WorkingTreeChange,
    collect_change_set,
    parse_name_status_z,
)


def test_name_status_parser_preserves_renames_and_unusual_paths():
    changes = parse_name_status_z("M\0src/white space.py\0R100\0old\tname.py\0new\nname.py\0")

    assert changes[0].path == "src/white space.py"
    assert changes[0].kind is ChangeKind.modified
    assert changes[1].previous_path == "old\tname.py"
    assert changes[1].path == "new\nname.py"


@patch("black_box_unlock.git.changes.run_git")
def test_working_tree_collects_only_unstaged_and_untracked(mock_git, tmp_path):
    (tmp_path / ".git").mkdir()
    mock_git.side_effect = [
        "head-oid\n",
        "M\0src/unstaged.py\0",
        "src/untracked.py\0",
    ]

    result = collect_change_set(tmp_path, WorkingTreeChange())

    assert [change.path for change in result.paths] == [
        "src/unstaged.py",
        "src/untracked.py",
    ]
    assert result.provenance.layers == ("unstaged", "untracked")


@patch("black_box_unlock.git.changes.run_git")
def test_staged_collects_only_the_index(mock_git, tmp_path):
    (tmp_path / ".git").mkdir()
    mock_git.side_effect = ["head-oid\n", "M\0src/staged.py\0"]

    result = collect_change_set(tmp_path, StagedChange())

    assert [change.path for change in result.paths] == ["src/staged.py"]
    assert result.provenance.layers == ("staged",)


@patch("black_box_unlock.git.changes.run_git")
def test_base_uses_merge_base_and_includes_all_local_layers(mock_git, tmp_path):
    (tmp_path / ".git").mkdir()
    mock_git.side_effect = [
        "base-oid\n",
        "head-oid\n",
        "merge-base-oid\n",
        "M\0src/branch.py\0",
        "src/untracked.py\0",
    ]

    result = collect_change_set(tmp_path, BaseChange(base_ref="origin/main"))

    assert result.provenance.merge_base_oid == "merge-base-oid"
    assert result.provenance.layers == (
        "committed",
        "staged",
        "unstaged",
        "untracked",
    )
    assert [change.path for change in result.paths] == [
        "src/branch.py",
        "src/untracked.py",
    ]
