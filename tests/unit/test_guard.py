"""Tests for the coupling guard's public interface and cache contract."""

import json
import os
import time
from unittest.mock import patch

import pytest

from black_box_unlock.guard import coupling_warnings
from tests.factories import make_commit


def _cache_payload(files: dict | None = None) -> dict:
    return {
        "version": 2,
        "generated_at": "2026-06-12T10:00:00Z",
        "head_oid": "unknown",
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


def _write_cache(repo, payload) -> None:
    cache = repo / ".bbu" / "cache.json"
    cache.parent.mkdir()
    cache.write_text(payload if isinstance(payload, str) else json.dumps(payload))


class TestCouplingWarnings:
    def test_warns_above_threshold_only(self, tmp_path):
        _write_cache(tmp_path, _cache_payload())

        warnings = coupling_warnings("src/auth.py", tmp_path, threshold=0.5)

        assert len(warnings) == 1
        assert "src/token.py" in warnings[0]
        assert "80%" in warnings[0]

    def test_tied_ratios_break_by_path_ascending(self, tmp_path):
        _write_cache(
            tmp_path,
            _cache_payload(
                {
                    "src/hub.py": [
                        {"file": "zeta.py", "ratio": 1.0, "shared_revisions": 2},
                        {"file": "alpha.py", "ratio": 1.0, "shared_revisions": 2},
                        {"file": "mid.py", "ratio": 1.0, "shared_revisions": 2},
                        {"file": "beta.py", "ratio": 1.0, "shared_revisions": 2},
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

    @patch("black_box_unlock.guard.fetch_git_history")
    def test_missing_cache_builds_minimal_versioned_snapshot(self, mock_history, tmp_path):
        mock_history.return_value = [
            make_commit(["src/auth.py", "src/token.py"]),
            make_commit(["src/auth.py", "src/token.py"]),
        ]

        warnings = coupling_warnings("src/auth.py", tmp_path)

        mock_history.assert_called_once_with(tmp_path, 90)
        assert "src/token.py" in warnings[0]
        payload = json.loads((tmp_path / ".bbu" / "cache.json").read_text())
        assert set(payload) == {
            "version",
            "generated_at",
            "head_oid",
            "files",
            "ignored_large_changesets",
        }
        assert (tmp_path / ".bbu" / ".gitignore").read_text() == "*\n"

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
        rebuilt = json.loads((tmp_path / ".bbu" / "cache.json").read_text())
        assert rebuilt["version"] == 2
        assert rebuilt["files"] == {}

    @patch("black_box_unlock.guard.fetch_git_history")
    def test_stale_cache_is_rebuilt(self, mock_history, tmp_path):
        _write_cache(tmp_path, _cache_payload())
        cache = tmp_path / ".bbu" / "cache.json"
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

    @pytest.mark.parametrize(
        ("threshold", "top"),
        [(-0.1, 3), (1.1, 3), (0.5, 0)],
    )
    def test_rejects_invalid_limits(self, threshold, top, tmp_path):
        with pytest.raises(ValueError):
            coupling_warnings("src/auth.py", tmp_path, threshold=threshold, top=top)
