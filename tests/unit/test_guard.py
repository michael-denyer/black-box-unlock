"""Tests for the coupling guard's public interface and cache contract."""

import json
import os
import subprocess
import time
from unittest.mock import patch

import pytest

from black_box_unlock.core.models import CouplingPolicy
from black_box_unlock.guard import coupling_warnings
from tests.factories import make_commit


def _cache_payload(files: dict | None = None) -> dict:
    return {
        "version": 3,
        "generated_at": "2026-06-12T10:00:00Z",
        "head_oid": "unknown",
        "max_changeset_size": 50,
        "require_live_partner": True,
        "files": files
        if files is not None
        else {
            "src/auth.py": [
                {
                    "file": "src/token.py",
                    "ratio": 0.8,
                    "shared_revisions": 8,
                    "file_revisions": 10,
                    "coupled_file_revisions": 10,
                    "confidence_lower_bound": 0.49,
                },
                {
                    "file": "src/util.py",
                    "ratio": 0.3,
                    "shared_revisions": 3,
                    "file_revisions": 10,
                    "coupled_file_revisions": 10,
                    "confidence_lower_bound": 0.11,
                },
            ]
        },
        "ignored_large_changesets": 0,
    }


def _git(repo, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def tmp_path(tmp_path):
    """Make every guard test directory a git repository; the cache lives in its git dir."""
    _git(tmp_path, "init", "-b", "main")
    return tmp_path


def _cache_file(repo):
    return repo / ".git" / "bbu" / "cache.json"


def _write_cache(repo, payload) -> None:
    cache = _cache_file(repo)
    cache.parent.mkdir()
    cache.write_text(payload if isinstance(payload, str) else json.dumps(payload))


def _commit_coupled_pair(repo) -> None:
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")
    for revision in ("1", "2"):
        (repo / "a.py").write_text(revision)
        (repo / "b.py").write_text(revision)
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", f"change {revision}")


class TestCacheSymlinkSafety:
    def test_committed_bbu_symlink_target_is_untouched(self, tmp_path):
        victim_dir = tmp_path.parent / f"{tmp_path.name}-victim"
        victim_dir.mkdir()
        (victim_dir / "cache.json").write_text("VICTIM")
        _commit_coupled_pair(tmp_path)
        (tmp_path / ".bbu").symlink_to(victim_dir)
        _git(tmp_path, "add", ".bbu")
        _git(tmp_path, "commit", "-m", "add symlink")

        first = coupling_warnings("a.py", tmp_path)
        second = coupling_warnings("a.py", tmp_path)

        assert "b.py" in first[0]
        assert second == first
        assert (victim_dir / "cache.json").read_text() == "VICTIM"
        assert sorted(p.name for p in victim_dir.iterdir()) == ["cache.json"]

    def test_symlinked_state_dir_is_not_written_through(self, tmp_path):
        victim_dir = tmp_path.parent / f"{tmp_path.name}-victim"
        victim_dir.mkdir()
        _commit_coupled_pair(tmp_path)
        _cache_file(tmp_path).parent.symlink_to(victim_dir)

        warnings = coupling_warnings("a.py", tmp_path)

        assert "b.py" in warnings[0]
        assert list(victim_dir.iterdir()) == []


class TestCacheWriteFailure:
    def test_unwritable_state_dir_still_returns_warnings(self, tmp_path):
        _commit_coupled_pair(tmp_path)
        state = _cache_file(tmp_path).parent
        state.mkdir()
        state.chmod(0o500)
        try:
            warnings = coupling_warnings("a.py", tmp_path)
        finally:
            state.chmod(0o700)

        assert "b.py" in warnings[0]
        assert not _cache_file(tmp_path).exists()


class TestCouplingWarnings:
    def test_warns_above_threshold_only(self, tmp_path):
        _write_cache(tmp_path, _cache_payload())

        warnings = coupling_warnings("src/auth.py", tmp_path, CouplingPolicy(min_ratio=0.5))

        assert len(warnings) == 1
        assert "src/token.py" in warnings[0]
        assert "8 of its 10 revisions (80%" in warnings[0]

    def test_threshold_applies_to_the_edited_files_share_not_the_symmetric_ratio(self, tmp_path):
        _write_cache(
            tmp_path,
            _cache_payload(
                {
                    "hub.py": [
                        {
                            "file": "leaf.py",
                            "ratio": 1.0,
                            "shared_revisions": 3,
                            "file_revisions": 30,
                            "coupled_file_revisions": 3,
                            "confidence_lower_bound": 0.44,
                        }
                    ],
                    "leaf.py": [
                        {
                            "file": "hub.py",
                            "ratio": 1.0,
                            "shared_revisions": 3,
                            "file_revisions": 3,
                            "coupled_file_revisions": 30,
                            "confidence_lower_bound": 0.44,
                        }
                    ],
                }
            ),
        )

        assert coupling_warnings("hub.py", tmp_path) == []
        assert "hub.py" in coupling_warnings("leaf.py", tmp_path)[0]

    def test_policy_comes_from_bbu_toml(self, tmp_path):
        _write_cache(tmp_path, _cache_payload())
        (tmp_path / ".bbu.toml").write_text("[coupling]\nmin_ratio = 0.9\n")

        assert coupling_warnings("src/auth.py", tmp_path) == []

    def test_tied_ratios_break_by_path_ascending(self, tmp_path):
        _write_cache(
            tmp_path,
            _cache_payload(
                {
                    "src/hub.py": [
                        {
                            "file": name,
                            "ratio": 1.0,
                            "shared_revisions": 2,
                            "file_revisions": 2,
                        }
                        for name in ("zeta.py", "alpha.py", "mid.py", "beta.py")
                    ]
                }
            ),
        )

        warnings = coupling_warnings("src/hub.py", tmp_path)

        assert "alpha.py" in warnings[0]
        assert "beta.py" in warnings[1]
        assert "mid.py" in warnings[2]
        assert "+1 more" in warnings[3]

    def test_unknown_file_has_no_warnings(self, tmp_path):
        _write_cache(tmp_path, _cache_payload())

        assert coupling_warnings("src/new.py", tmp_path) == []

    @patch("black_box_unlock.guard.head_paths")
    @patch("black_box_unlock.guard.fetch_git_history")
    def test_missing_cache_builds_minimal_versioned_snapshot(
        self, mock_history, mock_head_paths, tmp_path
    ):
        mock_history.return_value = [
            make_commit(["src/auth.py", "src/token.py"]),
            make_commit(["src/auth.py", "src/token.py"]),
        ]
        mock_head_paths.return_value = frozenset({"src/auth.py", "src/token.py"})

        warnings = coupling_warnings("src/auth.py", tmp_path)

        mock_history.assert_called_once_with(tmp_path, 90)
        assert "src/token.py" in warnings[0]
        payload = json.loads(_cache_file(tmp_path).read_text())
        assert set(payload) == {
            "version",
            "generated_at",
            "head_oid",
            "max_changeset_size",
            "require_live_partner",
            "files",
            "ignored_large_changesets",
            "dropped_deleted_partners",
        }

    @pytest.mark.parametrize(
        "payload",
        [
            "{ this is not valid json",
            "null",
            {"files": [{"path": "src/auth.py", "coupled_with": [{}]}]},
            _cache_payload({"src/auth.py": [{}]}),
        ],
    )
    @patch("black_box_unlock.guard.fetch_git_history")
    def test_unusable_fresh_cache_is_rebuilt(self, mock_history, payload, tmp_path):
        _write_cache(tmp_path, payload)
        mock_history.return_value = []

        assert coupling_warnings("src/auth.py", tmp_path) == []

        mock_history.assert_called_once_with(tmp_path, 90)
        rebuilt = json.loads(_cache_file(tmp_path).read_text())
        assert rebuilt["version"] == 3
        assert rebuilt["files"] == {}

    @patch("black_box_unlock.guard.fetch_git_history")
    def test_stale_cache_is_rebuilt(self, mock_history, tmp_path):
        _write_cache(tmp_path, _cache_payload())
        cache = _cache_file(tmp_path)
        old = time.time() - 25 * 3600
        os.utime(cache, (old, old))
        mock_history.return_value = []

        coupling_warnings("src/auth.py", tmp_path)

        mock_history.assert_called_once_with(tmp_path, 90)

    @patch("black_box_unlock.guard.fetch_git_history")
    def test_cache_from_another_head_is_rebuilt(self, mock_history, tmp_path):
        payload = _cache_payload()
        payload["head_oid"] = "old-head"
        _write_cache(tmp_path, payload)
        mock_history.return_value = []

        coupling_warnings("src/auth.py", tmp_path)

        mock_history.assert_called_once_with(tmp_path, 90)

    def test_one_off_evidence_does_not_warn(self, tmp_path):
        _write_cache(
            tmp_path,
            _cache_payload(
                {
                    "src/auth.py": [
                        {
                            "file": "src/one_off.py",
                            "ratio": 1.0,
                            "shared_revisions": 1,
                            "file_revisions": 1,
                            "coupled_file_revisions": 1,
                            "confidence_lower_bound": 0.21,
                        }
                    ]
                }
            ),
        )

        assert coupling_warnings("src/auth.py", tmp_path) == []

    @patch("black_box_unlock.guard.fetch_git_history")
    def test_cache_built_under_another_bulk_cap_is_rebuilt(self, mock_history, tmp_path):
        _write_cache(tmp_path, _cache_payload())
        mock_history.return_value = []

        coupling_warnings("src/auth.py", tmp_path, CouplingPolicy(max_changeset_size=80))

        mock_history.assert_called_once_with(tmp_path, 90)

    def test_rejects_invalid_top(self, tmp_path):
        with pytest.raises(ValueError):
            coupling_warnings("src/auth.py", tmp_path, top=0)


class TestLivePartners:
    def test_partner_deleted_at_head_does_not_warn(self, tmp_path):
        _commit_coupled_pair(tmp_path)
        _git(tmp_path, "rm", "b.py")
        _git(tmp_path, "commit", "-m", "remove b")

        assert coupling_warnings("a.py", tmp_path) == []
        payload = json.loads(_cache_file(tmp_path).read_text())
        assert payload["dropped_deleted_partners"] == 1

    def test_bulk_commit_is_not_coupling_evidence(self, tmp_path):
        _git(tmp_path, "config", "user.email", "dev@example.com")
        _git(tmp_path, "config", "user.name", "Dev")
        for revision in ("1", "2"):
            for index in range(3):
                (tmp_path / f"f{index}.py").write_text(revision)
            _git(tmp_path, "add", ".")
            _git(tmp_path, "commit", "-m", f"bulk {revision}")

        assert coupling_warnings("f0.py", tmp_path, CouplingPolicy(max_changeset_size=2)) == []
        assert coupling_warnings("f0.py", tmp_path, CouplingPolicy(max_changeset_size=3)) != []


class TestStateDirPerWorktree:
    def test_linked_worktree_keeps_its_own_cache(self, tmp_path):
        from black_box_unlock.guard import state_dir

        _commit_coupled_pair(tmp_path)
        linked = tmp_path.parent / f"{tmp_path.name}-linked"
        _git(tmp_path, "worktree", "add", str(linked), "-b", "linked")

        assert state_dir(tmp_path) != state_dir(linked)
        assert state_dir(tmp_path).resolve() == (tmp_path / ".git" / "bbu").resolve()
        assert (tmp_path / ".git" / "worktrees") in state_dir(linked).resolve().parents


class TestHookLogCap:
    def test_log_is_truncated_to_the_newest_lines(self, tmp_path):
        from black_box_unlock.guard import HOOK_LOG_MAX_LINES, hook_log_path, record_hook_failure

        _commit_coupled_pair(tmp_path)
        log = hook_log_path(tmp_path)
        log.parent.mkdir()
        log.write_text("".join(f"t{i} RuntimeError: old {i}\n" for i in range(HOOK_LOG_MAX_LINES)))

        record_hook_failure(tmp_path, RuntimeError("newest"))

        lines = log.read_text().splitlines()
        assert len(lines) == HOOK_LOG_MAX_LINES
        assert lines[0].endswith("old 1")
        assert lines[-1].endswith("RuntimeError: newest")
