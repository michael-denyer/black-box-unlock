"""Collect a selected change and review it against a fresh analysis."""

from datetime import datetime, timezone
from pathlib import Path

from ..analysis import SHALLOW_CLONE_WARNING, run_analysis
from ..core.models import SignalStatus
from ..git.changes import (
    BaseProvenance,
    ChangeKind,
    ChangeProvenance,
    ChangeSet,
    collect_change_set,
)
from ..git.run import is_shallow
from .models import ChangeReviewRequest, ChangeReviewResult, NoChanges
from .resolve import resolve_review_settings
from .rules import project_change_review


def _change_renames(change_set: ChangeSet) -> dict[str, str]:
    """Map each rename the change itself makes, which history cannot see yet, to its new path."""
    return {
        change.previous_path: change.path
        for change in change_set.paths
        if change.kind is ChangeKind.renamed and change.previous_path is not None
    }


def _history_end(provenance: ChangeProvenance) -> str | None:
    """End base-mode history at the merge base so the branch is not its own evidence."""
    return provenance.merge_base_oid if isinstance(provenance, BaseProvenance) else None


def run_change_review(
    repo_path: Path,
    request: ChangeReviewRequest,
) -> ChangeReviewResult:
    """Collect the selected change and analyze it afresh."""
    settings = resolve_review_settings(repo_path, request)
    policy = settings.parameters
    change_set = collect_change_set(repo_path, request.selector)
    if not change_set.paths:
        return NoChanges(
            repo=repo_path.resolve().name,
            generated_at=datetime.now(timezone.utc),
            provenance=change_set.provenance,
            parameters=policy,
            ci_status=SignalStatus(),
        )
    current_paths = frozenset(
        change.path for change in change_set.paths if change.kind is not ChangeKind.deleted
    )
    analysis = run_analysis(
        repo_path,
        days=policy.days,
        include_ci=policy.include_ci,
        xray_top=0,
        policy=policy.coupling,
        ensure_paths=current_paths,
        path_aliases=_change_renames(change_set),
        rev=_history_end(change_set.provenance),
    )
    return project_change_review(
        change_set,
        analysis,
        policy,
        path_role_rules=settings.path_roles,
        warnings=[SHALLOW_CLONE_WARNING] if is_shallow(repo_path) else [],
    )
