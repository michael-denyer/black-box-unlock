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
        "version": 1,
        "generated_at": "2026-06-12T10:00:00Z",
        "files": files
        if files is not None
        else {
            "src/auth.py": [
                {"file": "src/token.py", "ratio": 0.8},
                {"file": "src/util.py", "ratio": 0.3},
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
                        {"file": "zeta.py", "ratio": 1.0},
                        {"file": "alpha.py", "ratio": 1.0},
                        {"file": "mid.py", "ratio": 1.0},
                        {"file": "beta.py", "ratio": 1.0},
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
        assert rebuilt["version"] == 1
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

    @pytest.mark.parametrize(
        ("threshold", "top"),
        [(-0.1, 3), (1.1, 3), (0.5, 0)],
    )
    def test_rejects_invalid_limits(self, threshold, top, tmp_path):
        with pytest.raises(ValueError):
            coupling_warnings("src/auth.py", tmp_path, threshold=threshold, top=top)
