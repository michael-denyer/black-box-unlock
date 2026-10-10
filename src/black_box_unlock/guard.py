"""Fast temporal-coupling warnings for editor and agent hooks.

The guard owns a small, versioned cache containing only the coupling data it
reads. Building the cache scans git history once. It does not run complexity,
ownership, defect, CI, or X-Ray analysis.
"""

import os
import subprocess
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from loguru import logger
from pydantic import BaseModel, Field, ValidationError

from .config import resolve_coupling_policy
from .core.exceptions import BlackBoxUnlockError
from .core.models import CouplingInfo, CouplingPolicy, coupling_info_for, coupling_info_sort_key
from .git.coupling import analyze_temporal_coupling
from .git.log import exclude_bulk, fetch_git_history
from .git.run import head_paths, repo_toplevel, run_git

CACHE_FILENAME = "cache.json"
HOOK_LOG_FILENAME = "hook.log"
HOOK_LOG_MAX_LINES = 200
CACHE_MAX_AGE_HOURS = 24
CACHE_VERSION = 4
CACHE_HISTORY_DAYS = 90


class CouplingSnapshot(BaseModel):
    """The complete on-disk interface for the coupling guard.

    Every pair with at least one shared revision is stored, so the ratio and
    support floors apply at query time. The bulk cap and live-partner rule
    shape the stored pairs, so a snapshot built under other values is stale.
    """

    version: Literal[4] = CACHE_VERSION
    generated_at: datetime
    head_oid: str
    max_changeset_size: int = Field(ge=2)
    require_live_partner: bool
    files: dict[str, list[CouplingInfo]] = Field(default_factory=dict)
    ignored_large_changesets: int = Field(default=0, ge=0)
    dropped_deleted_partners: int = Field(default=0, ge=0)


def state_dir(repo_path: Path) -> Path:
    """Return bbu's state directory inside this worktree's git dir.

    The git dir is never populated from repository contents, so a committed
    symlink cannot redirect writes made here. Each linked worktree has its own
    git dir, so worktrees on different HEADs do not evict each other's cache.
    """
    git_dir = Path(run_git(repo_path, ["rev-parse", "--git-dir"]).strip())
    return repo_path / git_dir / "bbu"


def hook_log_path(path: Path) -> Path:
    """Return the edit hook's failure log for the repository containing path."""
    return state_dir(repo_toplevel(path)) / HOOK_LOG_FILENAME


def record_hook_failure(path: Path, error: Exception) -> None:
    """Append a timestamped line for a failure the edit hook swallowed. Never raises.

    The log keeps only the newest HOOK_LOG_MAX_LINES lines.
    """
    try:
        log = hook_log_path(path)
        if log.parent.is_symlink() or log.is_symlink():
            return
        log.parent.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        message = " ".join(str(error).split())
        lines = log.read_text().splitlines() if log.exists() else []
        lines.append(f"{stamp} {type(error).__name__}: {message}")
        log.write_text("\n".join(lines[-HOOK_LOG_MAX_LINES:]) + "\n")
    except Exception as log_error:
        logger.warning("could not record coupling guard hook failure: {}", log_error)


def _head_oid(repo_path: Path) -> str:
    try:
        return run_git(
            repo_path,
            ["rev-parse", "--verify", "HEAD^{commit}"],
            tolerate_unborn=True,
        ).strip()
    except (BlackBoxUnlockError, subprocess.CalledProcessError):
        return "unknown"


def _build_snapshot(repo_path: Path, head_oid: str, policy: CouplingPolicy) -> CouplingSnapshot:
    history, bulk_commits = exclude_bulk(
        fetch_git_history(repo_path, CACHE_HISTORY_DAYS), policy.max_changeset_size
    )
    live_paths = head_paths(repo_path) if policy.require_live_partner and history else None
    analysis = analyze_temporal_coupling(
        history,
        policy.model_copy(update={"min_ratio": 0.0, "min_shared_revisions": 1}),
        live_paths,
    )
    by_file: dict[str, list[CouplingInfo]] = defaultdict(list)
    for coupling in analysis.couplings:
        by_file[coupling.file_a].append(coupling_info_for(coupling, coupling.file_a))
        by_file[coupling.file_b].append(coupling_info_for(coupling, coupling.file_b))
    for coupled_files in by_file.values():
        coupled_files.sort(key=coupling_info_sort_key)
    return CouplingSnapshot(
        generated_at=datetime.now(timezone.utc),
        head_oid=head_oid,
        max_changeset_size=policy.max_changeset_size,
        require_live_partner=policy.require_live_partner,
        files=dict(by_file),
        ignored_large_changesets=bulk_commits,
        dropped_deleted_partners=analysis.dropped_deleted_partners,
    )


def _read_fresh_snapshot(
    cache: Path, head_oid: str, policy: CouplingPolicy
) -> CouplingSnapshot | None:
    if not cache.exists():
        return None
    try:
        age_seconds = time.time() - cache.stat().st_mtime
        if age_seconds >= CACHE_MAX_AGE_HOURS * 3600:
            return None
        snapshot = CouplingSnapshot.model_validate_json(cache.read_text())
        built_under = (
            snapshot.head_oid,
            snapshot.max_changeset_size,
            snapshot.require_live_partner,
        )
        wanted = (head_oid, policy.max_changeset_size, policy.require_live_partner)
        return snapshot if built_under == wanted else None
    except (OSError, ValidationError) as error:
        logger.warning("coupling cache at {} is unusable, rebuilding: {}", cache, error)
        return None


def _write_snapshot(cache: Path, snapshot: CouplingSnapshot) -> None:
    if cache.parent.is_symlink() or cache.is_symlink():
        logger.warning("refusing to write coupling cache through a symlink at {}", cache)
        return
    cache.parent.mkdir(exist_ok=True)
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


def _load_or_build_cache(repo_path: Path, policy: CouplingPolicy) -> CouplingSnapshot:
    cache = state_dir(repo_path) / CACHE_FILENAME
    head_oid = _head_oid(repo_path)
    snapshot = _read_fresh_snapshot(cache, head_oid, policy)
    if snapshot is not None:
        return snapshot
    snapshot = _build_snapshot(repo_path, head_oid, policy)
    try:
        _write_snapshot(cache, snapshot)
    except OSError as error:
        logger.warning("could not write coupling cache at {}: {}", cache, error)
    return snapshot


def coupling_warnings(  # [1c] Coupling guard for the edit hook
    file_path: str,
    repo_path: Path,
    policy: CouplingPolicy | None = None,
    top: int = 3,
) -> list[str]:
    """Return warnings for files strongly coupled to file_path.

    A partner warns when the share of file_path's revisions that also changed
    it reaches ``policy.min_ratio`` and the pair has at least
    ``policy.min_shared_revisions`` shared revisions. Editing a hub therefore
    stays quiet about leaves it once touched, while editing a leaf that always
    moves with the hub warns. Results are sorted by Wilson lower bound, shared
    revisions, observed ratio, and path. At most ``top`` detailed warnings are
    returned, followed by a summary when more matches exist.

    Args:
        file_path: Repo-relative path of the edited file.
        repo_path: Repository root.
        policy: Coupling policy; None reads ``.bbu.toml``.
        top: Maximum detailed warnings.
    """
    if top < 1:
        raise ValueError("top must be at least 1")
    policy = policy if policy is not None else resolve_coupling_policy(repo_path)

    snapshot = _load_or_build_cache(repo_path, policy)
    above = sorted(
        (
            item
            for item in snapshot.files.get(file_path, [])
            if item.rate_to_partner >= policy.min_ratio
            and item.shared_revisions >= policy.min_shared_revisions
        ),
        key=coupling_info_sort_key,
    )
    warnings = [
        f"{file_path} historically co-changes with {item.file} in "
        f"{item.shared_revisions} of its {item.file_revisions} revisions "
        f"({round(item.rate_to_partner * 100)}%, 95% lower bound "
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
