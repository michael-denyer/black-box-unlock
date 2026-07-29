"""Fast temporal-coupling warnings for editor and agent hooks.

The guard owns a small, versioned cache containing only the coupling data it
reads. Building the cache scans git history once. It does not run complexity,
ownership, defect, CI, or X-Ray analysis.
"""

import os
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from loguru import logger
from pydantic import BaseModel, Field, ValidationError

from .core.models import CouplingInfo
from .git.coupling import analyze_temporal_coupling
from .git.log import fetch_git_history

CACHE_RELPATH = Path(".bbu") / "cache.json"
CACHE_MAX_AGE_HOURS = 24
CACHE_VERSION = 1
CACHE_HISTORY_DAYS = 90


class CouplingSnapshot(BaseModel):
    """The complete on-disk interface for the coupling guard."""

    version: Literal[1] = CACHE_VERSION
    generated_at: datetime
    files: dict[str, list[CouplingInfo]] = Field(default_factory=dict)
    ignored_large_changesets: int = Field(default=0, ge=0)


def _build_snapshot(repo_path: Path) -> CouplingSnapshot:
    history = fetch_git_history(repo_path, CACHE_HISTORY_DAYS)
    analysis = analyze_temporal_coupling(history, min_ratio=0.0)
    by_file: dict[str, list[CouplingInfo]] = defaultdict(list)
    for coupling in analysis.couplings:
        by_file[coupling.file_a].append(
            CouplingInfo(file=coupling.file_b, ratio=coupling.coupling_ratio)
        )
        by_file[coupling.file_b].append(
            CouplingInfo(file=coupling.file_a, ratio=coupling.coupling_ratio)
        )
    for coupled_files in by_file.values():
        coupled_files.sort(key=lambda item: (-item.ratio, item.file))
    return CouplingSnapshot(
        generated_at=datetime.now(timezone.utc),
        files=dict(by_file),
        ignored_large_changesets=analysis.ignored_large_changesets,
    )


def _read_fresh_snapshot(cache: Path) -> CouplingSnapshot | None:
    if not cache.exists():
        return None
    try:
        age_seconds = time.time() - cache.stat().st_mtime
        if age_seconds >= CACHE_MAX_AGE_HOURS * 3600:
            return None
        return CouplingSnapshot.model_validate_json(cache.read_text())
    except (OSError, ValidationError) as error:
        logger.warning("coupling cache at {} is unusable, rebuilding: {}", cache, error)
        return None


def _write_snapshot(cache: Path, snapshot: CouplingSnapshot) -> None:
    cache.parent.mkdir(exist_ok=True)
    (cache.parent / ".gitignore").write_text("*\n")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            dir=cache.parent,
            prefix=".cache-",
            suffix=".json.tmp",
            delete=False,
        ) as temporary:
            temporary.write(snapshot.model_dump_json(indent=2))
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, cache)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _load_or_build_cache(repo_path: Path) -> CouplingSnapshot:
    cache = repo_path / CACHE_RELPATH
    snapshot = _read_fresh_snapshot(cache)
    if snapshot is not None:
        return snapshot
    snapshot = _build_snapshot(repo_path)
    _write_snapshot(cache, snapshot)
    return snapshot


def coupling_warnings(
    file_path: str,
    repo_path: Path,
    threshold: float = 0.5,
    top: int = 3,
) -> list[str]:
    """Return warnings for files strongly coupled to file_path.

    Results are sorted by coupling ratio and path. At most ``top`` detailed
    warnings are returned, followed by a summary when more matches exist.
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")
    if top < 1:
        raise ValueError("top must be at least 1")

    snapshot = _load_or_build_cache(repo_path)
    above = sorted(
        (item for item in snapshot.files.get(file_path, []) if item.ratio >= threshold),
        key=lambda item: (-item.ratio, item.file),
    )
    warnings = [
        f"{file_path} historically co-changes with {item.file} "
        f"{round(item.ratio * 100)}% of the time - check whether that file "
        "needs the same change"
        for item in above[:top]
    ]
    remainder = len(above) - top
    if remainder > 0:
        warnings.append(
            f"+{remainder} more files also co-change with {file_path} "
            "(run bbu analyze-repo for the full list)"
        )
    return warnings
