"""Ambient coupling guard for editor/agent hooks.

Reads a cached analysis (rebuilding it if stale) and reports files temporally
coupled to the one just edited. Must be fast and must never break an edit:
failures degrade to silence by design.

The cache reflects history as of its last build (up to 24h old) and assumes
the hook runs from the repository root.
"""

import json
import time
from pathlib import Path
from typing import Any

from loguru import logger

from .analysis import export_to_json, run_analysis

CACHE_RELPATH = Path(".bbu") / "cache.json"
CACHE_MAX_AGE_HOURS = 24


def _cache_is_usable(data: Any) -> bool:
    """True when the cache has the shape coupling_warnings reads (dict with a
    list of file dicts, each carrying a path)."""
    return (
        isinstance(data, dict)
        and isinstance(data.get("files"), list)
        and all(isinstance(f, dict) and "path" in f for f in data["files"])
    )


def _load_or_build_cache(repo_path: Path) -> dict[str, Any]:
    cache = repo_path / CACHE_RELPATH
    if cache.exists() and time.time() - cache.stat().st_mtime < CACHE_MAX_AGE_HOURS * 3600:
        # A corrupt or wrong-shape cache must not disable the guard: rebuild rather
        # than crash or re-warn on every edit until the TTL expires.
        try:
            data = json.loads(cache.read_text())
        except json.JSONDecodeError as e:
            logger.warning("coupling cache at {} is unreadable, rebuilding: {}", cache, e)
        else:
            if _cache_is_usable(data):
                return data
            logger.warning("coupling cache at {} has an unexpected shape, rebuilding", cache)
    result = run_analysis(repo_path, days=90, include_ci=False)
    payload = export_to_json(result)
    cache.parent.mkdir(exist_ok=True)
    (cache.parent / ".gitignore").write_text("*\n")  # self-ignoring: never litter the analyzed repo
    cache.write_text(payload)
    return json.loads(payload)


def coupling_warnings(
    file_path: str, repo_path: Path, threshold: float = 0.5, top: int = 3
) -> list[str]:
    """Warnings for files strongly coupled to file_path (repo-relative).

    Returns at most `top` warnings, sorted by coupling ratio descending. If
    more files exceed the threshold beyond the cap, appends a single summary
    line with the count.
    """
    data = _load_or_build_cache(repo_path)
    for f in data.get("files", []):
        if f["path"] == file_path:
            above = sorted(
                [c for c in f.get("coupled_with", []) if c["ratio"] >= threshold],
                key=lambda c: (-c["ratio"], c["file"]),
            )
            warnings = [
                f"{file_path} historically co-changes with {c['file']} "
                f"{round(c['ratio'] * 100)}% of the time - check whether that file "
                "needs the same change"
                for c in above[:top]
            ]
            remainder = len(above) - top
            if remainder > 0:
                warnings.append(
                    f"+{remainder} more files also co-change with {file_path} "
                    "(run bbu analyze-repo for the full list)"
                )
            return warnings
    return []
