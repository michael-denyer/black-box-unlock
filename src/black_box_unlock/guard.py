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

from .core.exceptions import BlackBoxUnlockError
from .core.models import CouplingInfo, coupling_info_for, coupling_info_sort_key
from .git.coupling import analyze_temporal_coupling
from .git.log import fetch_git_history
from .git.run import run_git

CACHE_RELPATH = Path(".bbu") / "cache.json"
CACHE_MAX_AGE_HOURS = 24
CACHE_VERSION = 2
CACHE_HISTORY_DAYS = 90


class CouplingSnapshot(BaseModel):
    """The complete on-disk interface for the coupling guard."""

    version: Literal[2] = CACHE_VERSION
    generated_at: datetime
    head_oid: str
    files: dict[str, list[CouplingInfo]] = Field(default_factory=dict)
    ignored_large_changesets: int = Field(default=0, ge=0)


def _head_oid(repo_path: Path) -> str:
    try:
        return run_git(
            repo_path,
            ["rev-parse", "--verify", "HEAD^{commit}"],
            tolerate_unborn=True,
        ).strip()
    except BlackBoxUnlockError:
        return "unknown"


def _build_snapshot(repo_path: Path, head_oid: str) -> CouplingSnapshot:
    history = fetch_git_history(repo_path, CACHE_HISTORY_DAYS)
    analysis = analyze_temporal_coupling(history, min_ratio=0.0)
    by_file: dict[str, list[CouplingInfo]] = defaultdict(list)
    for coupling in analysis.couplings:
        by_file[coupling.file_a].append(coupling_info_for(coupling, coupling.file_a))
        by_file[coupling.file_b].append(coupling_info_for(coupling, coupling.file_b))
    for coupled_files in by_file.values():
        coupled_files.sort(key=coupling_info_sort_key)
    return CouplingSnapshot(
        generated_at=datetime.now(timezone.utc),
        head_oid=head_oid,
        files=dict(by_file),
        ignored_large_changesets=analysis.ignored_large_changesets,
    )


def _read_fresh_snapshot(cache: Path, head_oid: str) -> CouplingSnapshot | None:
    if not cache.exists():
        return None
    try:
        age_seconds = time.time() - cache.stat().st_mtime
        if age_seconds >= CACHE_MAX_AGE_HOURS * 3600:
            return None
        snapshot = CouplingSnapshot.model_validate_json(cache.read_text())
        return snapshot if snapshot.head_oid == head_oid else None
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
    head_oid = _head_oid(repo_path)
    snapshot = _read_fresh_snapshot(cache, head_oid)
    if snapshot is not None:
        return snapshot
    snapshot = _build_snapshot(repo_path, head_oid)
    _write_snapshot(cache, snapshot)
    return snapshot


def coupling_warnings(
    file_path: str,
    repo_path: Path,
    threshold: float = 0.5,
    top: int = 3,
    min_shared_revisions: int = 2,
) -> list[str]:
    """Return warnings for files strongly coupled to file_path.

    Results are sorted by Wilson lower bound, shared revisions, observed ratio,
    and path. At most ``top`` detailed warnings are returned, followed by a
    summary when more matches exist.
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")
    if top < 1:
        raise ValueError("top must be at least 1")
    if min_shared_revisions < 1:
        raise ValueError("min_shared_revisions must be at least 1")

    snapshot = _load_or_build_cache(repo_path)
    above = sorted(
        (
            item
            for item in snapshot.files.get(file_path, [])
            if item.ratio >= threshold and item.shared_revisions >= min_shared_revisions
        ),
        key=coupling_info_sort_key,
    )
    warnings = [
        f"{file_path} historically co-changes with {item.file} "
        f"{item.shared_revisions} times "
        f"({round(item.ratio * 100)}%, 95% lower bound "
        f"{round(item.confidence_lower_bound * 100)}%) - check whether that file "
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
