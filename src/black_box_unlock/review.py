"""Fresh, evidence-backed review of a selected Git change."""

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from .analysis import run_analysis
from .core.models import AnalysisResult, FileForensics, SignalStatus
from .git.changes import (
    ChangedPath,
    ChangeKind,
    ChangeProvenance,
    ChangeSelector,
    ChangeSet,
    collect_change_set,
)

MAX_REVIEW_COUPLINGS = 20


class PathRole(str, Enum):
    """Stable, coarse role of a repository path."""

    source = "source"
    test = "test"
    docs = "docs"
    config = "config"
    migration = "migration"
    generated = "generated"
    other = "other"


class PathRoleClassification(BaseModel):
    """A role plus the fixed rule that selected it."""

    role: PathRole
    rule: str


class ReviewParameters(BaseModel):
    """Public policies needed to interpret a review."""

    days: int = Field(default=90, ge=1)
    min_coupling: float = Field(default=0.3, ge=0.0, le=1.0)
    min_shared_revisions: int = Field(default=2, ge=1)
    include_ci: bool = False
    max_actions: int = Field(default=3, ge=1, le=3)


class FileEvidence(BaseModel):
    """Historical facts retained for one selected path."""

    path: str
    role: PathRoleClassification
    commits: int = Field(ge=0)
    complexity: float = Field(ge=0)
    bugfix_commits: int = Field(ge=0)
    author_count: int = Field(ge=0)
    build_failures: int = Field(ge=0)


class ChangedFileReview(BaseModel):
    """A selected path joined with its historical facts."""

    change: ChangedPath
    evidence: FileEvidence


class CouplingEvidence(BaseModel):
    """Explainable historical relationship involving a selected path."""

    changed_path: str
    changed_path_role: PathRoleClassification
    coupled_path: str
    coupled_path_role: PathRoleClassification
    shared_revisions: int = Field(ge=1)
    changed_path_revisions: int = Field(ge=1)
    coupled_path_revisions: int = Field(ge=1)
    coupling_ratio: float = Field(ge=0.0, le=1.0)
    confidence_lower_bound: float = Field(ge=0.0, le=1.0)
    coupled_path_is_changed: bool


class TestGapEvidence(BaseModel):
    """Selected source paths with no selected test path."""

    source_paths: list[str] = Field(min_length=1)
    changed_test_paths: list[str]
    role_classifier_version: Literal[1] = 1


class FocusFileEvidence(BaseModel):
    """Defect and ownership facts that justify focused review."""

    path: str
    bugfix_commits: int = Field(ge=0)
    author_count: int = Field(ge=0)
    commits: int = Field(ge=0)
    complexity: float = Field(ge=0)


class CheckCoupledPathsAction(BaseModel):
    kind: Literal["check_coupled_paths"] = "check_coupled_paths"
    message: str
    evidence: list[CouplingEvidence] = Field(min_length=1, max_length=3)


class AddOrUpdateTestsAction(BaseModel):
    kind: Literal["add_or_update_tests"] = "add_or_update_tests"
    message: str
    evidence: TestGapEvidence


class FocusReviewAction(BaseModel):
    kind: Literal["focus_review"] = "focus_review"
    message: str
    evidence: list[FocusFileEvidence] = Field(min_length=1, max_length=3)


ReviewAction = Annotated[
    CheckCoupledPathsAction | AddOrUpdateTestsAction | FocusReviewAction,
    Field(discriminator="kind"),
]


class ChangeReview(BaseModel):
    """A selected change plus bounded, evidence-backed actions."""

    kind: Literal["review"] = "review"
    repo: str
    generated_at: datetime
    provenance: ChangeProvenance
    parameters: ReviewParameters
    files: list[ChangedFileReview]
    couplings: list[CouplingEvidence] = Field(max_length=MAX_REVIEW_COUPLINGS)
    actions: list[ReviewAction] = Field(max_length=3)
    ci_status: SignalStatus


class NoChanges(BaseModel):
    """The selector resolved successfully but selected no paths."""

    kind: Literal["no_changes"] = "no_changes"
    repo: str
    generated_at: datetime
    provenance: ChangeProvenance
    parameters: ReviewParameters
    ci_status: SignalStatus = Field(default_factory=SignalStatus)


ChangeReviewResult = Annotated[
    ChangeReview | NoChanges,
    Field(discriminator="kind"),
]

_TEST_SEGMENTS = frozenset({"test", "tests", "spec", "specs", "__tests__"})
_DOC_SEGMENTS = frozenset({"doc", "docs", "documentation"})
_MIGRATION_SEGMENTS = frozenset({"migration", "migrations"})
_GENERATED_SEGMENTS = frozenset({"generated", "vendor", "node_modules"})
_CONFIG_SEGMENTS = frozenset({"config", "hooks", ".claude-plugin", ".github"})
_DOC_SUFFIXES = frozenset({".md", ".mdx", ".rst", ".adoc"})
_CONFIG_SUFFIXES = frozenset({".toml", ".yaml", ".yml", ".ini", ".cfg"})
_SOURCE_SUFFIXES = frozenset(
    {
        ".c",
        ".cc",
        ".cpp",
        ".cs",
        ".go",
        ".java",
        ".js",
        ".jsx",
        ".kt",
        ".php",
        ".py",
        ".rb",
        ".rs",
        ".scala",
        ".swift",
        ".ts",
        ".tsx",
    }
)
_ACTIONABLE_ROLES = frozenset({PathRole.source, PathRole.migration, PathRole.config})


def classify_path_role(path: str) -> PathRoleClassification:
    """Classify a path with fixed, ordered, explainable rules."""
    candidate = Path(path)
    lowered_parts = {part.lower() for part in candidate.parts}
    name = candidate.name.lower()
    suffix = candidate.suffix.lower()

    if lowered_parts & _TEST_SEGMENTS or name.startswith(("test_", "test.", "spec_")):
        return PathRoleClassification(role=PathRole.test, rule="test-path")
    if lowered_parts & _DOC_SEGMENTS or suffix in _DOC_SUFFIXES:
        return PathRoleClassification(role=PathRole.docs, rule="docs-path")
    if lowered_parts & _MIGRATION_SEGMENTS:
        return PathRoleClassification(role=PathRole.migration, rule="migration-path")
    if (
        lowered_parts & _GENERATED_SEGMENTS
        or suffix in {".lock", ".map"}
        or name.endswith((".min.js", ".min.css"))
    ):
        return PathRoleClassification(role=PathRole.generated, rule="generated-path")
    if (
        lowered_parts & _CONFIG_SEGMENTS
        or suffix in _CONFIG_SUFFIXES
        or name in {"dockerfile", "makefile", "pyproject.toml", "package.json"}
    ):
        return PathRoleClassification(role=PathRole.config, rule="config-path")
    if suffix in _SOURCE_SUFFIXES:
        return PathRoleClassification(role=PathRole.source, rule="source-extension")
    return PathRoleClassification(role=PathRole.other, rule="fallback")


def _empty_forensics(path: str) -> FileForensics:
    return FileForensics(
        path=path,
        commits=0,
        lines_changed=0,
        authors=[],
        coupled_with=[],
    )


def _file_evidence(path: str, forensics: FileForensics) -> FileEvidence:
    return FileEvidence(
        path=path,
        role=classify_path_role(path),
        commits=forensics.commits,
        complexity=forensics.complexity,
        bugfix_commits=forensics.bugfix_commits,
        author_count=forensics.author_count,
        build_failures=forensics.build_failures,
    )


def _coupling_evidence(
    change_set: ChangeSet,
    analysis: AnalysisResult,
    parameters: ReviewParameters,
) -> list[CouplingEvidence]:
    aliases: dict[str, str] = {}
    selected_paths = {change.path for change in change_set.paths}
    for change in change_set.paths:
        aliases[change.path] = change.path
        if change.previous_path is not None:
            aliases[change.previous_path] = change.path

    evidence: dict[tuple[str, str], CouplingEvidence] = {}
    for coupling in analysis.couplings:
        if coupling.co_change_count < parameters.min_shared_revisions:
            continue
        a_selected = coupling.file_a in aliases
        b_selected = coupling.file_b in aliases
        if not (a_selected or b_selected):
            continue
        if a_selected:
            changed_path = aliases[coupling.file_a]
            coupled_path = aliases.get(coupling.file_b, coupling.file_b)
            changed_revisions = coupling.commits_a
            coupled_revisions = coupling.commits_b
        else:
            changed_path = aliases[coupling.file_b]
            coupled_path = aliases.get(coupling.file_a, coupling.file_a)
            changed_revisions = coupling.commits_b
            coupled_revisions = coupling.commits_a
        if changed_path == coupled_path:
            continue
        item = CouplingEvidence(
            changed_path=changed_path,
            changed_path_role=classify_path_role(changed_path),
            coupled_path=coupled_path,
            coupled_path_role=classify_path_role(coupled_path),
            shared_revisions=coupling.co_change_count,
            changed_path_revisions=changed_revisions,
            coupled_path_revisions=coupled_revisions,
            coupling_ratio=coupling.coupling_ratio,
            confidence_lower_bound=coupling.confidence_lower_bound,
            coupled_path_is_changed=coupled_path in selected_paths,
        )
        key = (changed_path, coupled_path)
        current = evidence.get(key)
        if current is None or item.confidence_lower_bound > current.confidence_lower_bound:
            evidence[key] = item

    return sorted(
        evidence.values(),
        key=lambda item: (
            -item.confidence_lower_bound,
            -item.shared_revisions,
            -item.coupling_ratio,
            item.changed_path,
            item.coupled_path,
        ),
    )


def project_change_review(
    change_set: ChangeSet,
    analysis: AnalysisResult,
    parameters: ReviewParameters,
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
    files = [
        ChangedFileReview(
            change=change,
            evidence=_file_evidence(
                change.path,
                by_path.get(change.path, _empty_forensics(change.path)),
            ),
        )
        for change in change_set.paths
    ]
    couplings = _coupling_evidence(change_set, analysis, parameters)
    actions: list[ReviewAction] = []

    missing = [
        item
        for item in couplings
        if not item.coupled_path_is_changed and item.changed_path_role.role in _ACTIONABLE_ROLES
    ]
    if missing:
        actions.append(
            CheckCoupledPathsAction(
                message="Check whether historically coupled paths need the same change.",
                evidence=missing[:3],
            )
        )

    source_paths = sorted(
        file.change.path
        for file in files
        if file.evidence.role.role in {PathRole.source, PathRole.migration}
        and file.change.kind is not ChangeKind.deleted
    )
    test_paths = sorted(
        file.change.path
        for file in files
        if file.evidence.role.role is PathRole.test and file.change.kind is not ChangeKind.deleted
    )
    if source_paths and not test_paths:
        actions.append(
            AddOrUpdateTestsAction(
                message="Confirm the changed source behavior is covered by tests.",
                evidence=TestGapEvidence(
                    source_paths=source_paths,
                    changed_test_paths=test_paths,
                ),
            )
        )

    focus = [
        FocusFileEvidence(
            path=file.change.path,
            bugfix_commits=file.evidence.bugfix_commits,
            author_count=file.evidence.author_count,
            commits=file.evidence.commits,
            complexity=file.evidence.complexity,
        )
        for file in files
        if file.evidence.role.role in _ACTIONABLE_ROLES
        and (file.evidence.bugfix_commits > 0 or file.evidence.author_count > 3)
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
    if focus:
        actions.append(
            FocusReviewAction(
                message="Focus review on changed files with defect or ownership history.",
                evidence=focus[:3],
            )
        )

    return ChangeReview(
        repo=analysis.repo,
        generated_at=analysis.generated_at,
        provenance=change_set.provenance,
        parameters=parameters,
        files=files,
        couplings=couplings[:MAX_REVIEW_COUPLINGS],
        actions=actions[: parameters.max_actions],
        ci_status=analysis.ci_status,
    )


def run_change_review(
    repo_path: Path,
    selector: ChangeSelector,
    parameters: ReviewParameters | None = None,
) -> ChangeReviewResult:
    """Collect the selected change and analyze it afresh."""
    policy = parameters or ReviewParameters()
    change_set = collect_change_set(repo_path, selector)
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
        min_coupling=policy.min_coupling,
        include_ci=policy.include_ci,
        xray_top=0,
        ensure_paths=current_paths,
    )
    return project_change_review(change_set, analysis, policy)
