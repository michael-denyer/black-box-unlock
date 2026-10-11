"""The bounded action policy: pure rules over the facts of one review."""

from collections.abc import Callable
from dataclasses import dataclass

from ..core.models import AnalysisResult
from ..git.changes import ChangeKind, ChangeSet
from ..git.ownership import OwnershipRisk, ownership_risk
from ..path_roles import PathRole, PathRoleRule
from .evidence import ci_failure_evidence, coupling_evidence, empty_forensics, file_evidence
from .models import (
    MAX_REVIEW_COUPLINGS,
    AddOrUpdateTestsAction,
    ChangedFileReview,
    ChangeReview,
    ChangeReviewResult,
    CheckCoupledPathsAction,
    CouplingEvidence,
    FocusFileEvidence,
    FocusReviewAction,
    InspectCIFailuresAction,
    NoChanges,
    ReviewAction,
    ReviewParameters,
    TestGapEvidence,
)

ACTIONABLE_ROLES = frozenset({PathRole.source, PathRole.migration, PathRole.config})


@dataclass(frozen=True)
class ReviewFacts:
    """Everything a rule may read: the selected change, its joined files and couplings, the analysis, and the policy."""

    change_set: ChangeSet
    files: list[ChangedFileReview]
    couplings: list[CouplingEvidence]
    analysis: AnalysisResult
    parameters: ReviewParameters


def check_coupled_paths(facts: ReviewFacts) -> ReviewAction | None:
    missing = [
        item
        for item in facts.couplings
        if not item.coupled_path_is_changed and item.changed_path_role.role in ACTIONABLE_ROLES
    ]
    if not missing:
        return None
    return CheckCoupledPathsAction(
        message="Check whether historically coupled paths need the same change.",
        evidence=missing[:3],
    )


def add_or_update_tests(facts: ReviewFacts) -> ReviewAction | None:
    source_paths = sorted(
        file.change.path
        for file in facts.files
        if file.evidence.role.role in {PathRole.source, PathRole.migration}
        and file.change.kind is not ChangeKind.deleted
    )
    test_paths = sorted(
        file.change.path
        for file in facts.files
        if file.evidence.role.role is PathRole.test and file.change.kind is not ChangeKind.deleted
    )
    if not source_paths or test_paths:
        return None
    return AddOrUpdateTestsAction(
        message="Confirm the changed source behavior is covered by tests.",
        evidence=TestGapEvidence(source_paths=source_paths, changed_test_paths=test_paths),
    )


def inspect_ci_failures(facts: ReviewFacts) -> ReviewAction | None:
    if not facts.parameters.include_ci:
        return None
    selected_paths = {change.path for change in facts.change_set.paths}
    failures = ci_failure_evidence(facts.analysis, selected_paths)
    if not failures:
        return None
    return InspectCIFailuresAction(
        message=(
            "Inspect failed workflow runs containing changed paths. "
            "The paths are implicated by the failed commit, not proven causal."
        ),
        evidence=failures[:3],
    )


def focus_review(facts: ReviewFacts) -> ReviewAction | None:
    focus = [
        FocusFileEvidence(
            path=file.change.path,
            bugfix_commits=file.evidence.bugfix_commits,
            author_count=file.evidence.author_count,
            main_author_share=file.evidence.main_author_share,
            commits=file.evidence.commits,
            complexity=file.evidence.complexity,
        )
        for file in facts.files
        if file.evidence.role.role in ACTIONABLE_ROLES
        and (
            file.evidence.bugfix_commits > 0
            or ownership_risk(file.evidence) is OwnershipRisk.diffuse
        )
    ]
    focus.sort(
        key=lambda item: (
            -item.bugfix_commits,
            -item.author_count,
            -item.commits,
            -item.complexity,
            item.path,
        )
    )
    if not focus:
        return None
    return FocusReviewAction(
        message="Focus review on changed files with defect or ownership history.",
        evidence=focus[:3],
    )


RULES: tuple[Callable[[ReviewFacts], ReviewAction | None], ...] = (
    check_coupled_paths,
    add_or_update_tests,
    inspect_ci_failures,
    focus_review,
)
"""Rules run in this order; the first ``max_actions`` results are kept."""


def project_change_review(
    change_set: ChangeSet,
    analysis: AnalysisResult,
    parameters: ReviewParameters,
    path_role_rules: tuple[PathRoleRule, ...] = (),
    warnings: list[str] | None = None,
) -> ChangeReviewResult:
    """Purely join selected paths, repository facts, and bounded action policy."""
    if not change_set.paths:
        return NoChanges(
            repo=analysis.repo,
            generated_at=analysis.generated_at,
            provenance=change_set.provenance,
            parameters=parameters,
            ci_status=analysis.ci_status,
        )

    by_path = {file.path: file for file in analysis.files}
    facts = ReviewFacts(
        change_set=change_set,
        files=[
            ChangedFileReview(
                change=change,
                evidence=file_evidence(
                    change.path,
                    by_path.get(change.path) or empty_forensics(change.path, path_role_rules),
                    path_role_rules,
                ),
            )
            for change in change_set.paths
        ],
        couplings=coupling_evidence(change_set, analysis, parameters, path_role_rules),
        analysis=analysis,
        parameters=parameters,
    )
    actions = [action for rule in RULES if (action := rule(facts)) is not None]
    kept_actions = actions[: parameters.max_actions]
    return ChangeReview(
        repo=analysis.repo,
        generated_at=analysis.generated_at,
        provenance=change_set.provenance,
        parameters=parameters,
        files=facts.files,
        couplings=facts.couplings[:MAX_REVIEW_COUPLINGS],
        actions=kept_actions,
        omitted_actions=len(actions) - len(kept_actions),
        warnings=warnings or [],
        ci_status=analysis.ci_status,
    )
