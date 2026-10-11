"""Tests for the history window shared by analysis and the guard."""

from pathlib import Path
from unittest.mock import patch

from black_box_unlock.core.models import CouplingPolicy
from black_box_unlock.git.history import load_history_window
from tests.factories import make_commit

REPO = Path("/fake/repo")


def _window(commits, policy=CouplingPolicy(), *, tree=frozenset(), **kwargs):
    with (
        patch("black_box_unlock.git.history.fetch_git_history", return_value=commits) as fetch,
        patch("black_box_unlock.git.history.head_paths", return_value=tree),
    ):
        window = load_history_window(REPO, 30, policy, **kwargs)
    return window, fetch


def test_bulk_commits_are_dropped_and_counted():
    bulk = make_commit([f"f{n}.py" for n in range(3)])
    window, _ = _window([make_commit(["a.py"]), bulk], CouplingPolicy(max_changeset_size=2))

    assert [f.path for c in window.commits for f in c.files] == ["a.py"]
    assert window.ignored_bulk_commits == 1


def test_live_paths_join_the_tree_with_ensured_and_aliased_paths():
    window, fetch = _window(
        [make_commit(["a.py"])],
        tree=frozenset({"a.py"}),
        ensure_paths=frozenset({"new.py"}),
        aliases={"a.py": "b.py"},
    )

    assert window.live_paths == frozenset({"a.py", "new.py", "b.py"})
    fetch.assert_called_once_with(REPO, 30, None, aliases={"a.py": "b.py"})


def test_live_paths_are_none_when_deleted_partners_are_kept_or_history_is_empty():
    kept, _ = _window([make_commit(["a.py"])], CouplingPolicy(require_live_partner=False))
    empty, _ = _window([], tree=frozenset({"a.py"}))

    assert kept.live_paths is None
    assert empty.live_paths is None


def test_rename_identity_runs_both_ways_and_includes_caller_aliases():
    history = [
        make_commit(files=[{"path": "b.py", "former_paths": ["a.py"]}]),
        make_commit(files=[{"path": "c.py", "former_paths": ["d.py"]}, {"path": "d.py"}]),
    ]
    window, _ = _window(history, aliases={"c.py": "e.py"})

    assert window.renamed_from == {"b.py": ["a.py"], "c.py": ["d.py"]}
    assert window.aliases == {"a.py": "b.py", "c.py": "e.py"}
