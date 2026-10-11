"""Historical facts projected onto the selected paths."""

from ..core.models import AnalysisResult, FileForensics, coupling_info_for
from ..git.changes import ChangeSet
from ..path_roles import PathRoleRule, classify_path_role
from .models import CIFailureEvidence, CouplingEvidence, FileEvidence, ReviewParameters


def empty_forensics(path: str, path_role_rules: tuple[PathRoleRule, ...]) -> FileForensics:
    return FileForensics(
        path=path,
        path_role=classify_path_role(path, path_role_rules).role,
        commits=0,
        lines_changed=0,
        authors=[],
        coupled_with=[],
    )


def file_evidence(
    path: str,
    forensics: FileForensics,
    path_role_rules: tuple[PathRoleRule, ...],
) -> FileEvidence:
    return FileEvidence(
        path=path,
        role=classify_path_role(path, path_role_rules),
        commits=forensics.commits,
        complexity=forensics.complexity,
        bugfix_commits=forensics.bugfix_commits,
        author_count=forensics.author_count,
        main_author_share=forensics.main_author_share,
        build_failures=forensics.build_failures,
    )


def coupling_evidence(
    change_set: ChangeSet,
    analysis: AnalysisResult,
    parameters: ReviewParameters,
    path_role_rules: tuple[PathRoleRule, ...],
) -> list[CouplingEvidence]:
    """Orient each pair from the changed path and keep partners it usually moves with.

    The analysis already applied the support floor and live-partner rule and
    reports every path under its current name. The ratio floor applies to the
    directional rate shared / changed-path revisions.
    """
    selected_paths = {change.path for change in change_set.paths}

    evidence: dict[tuple[str, str], CouplingEvidence] = {}
    for coupling in analysis.couplings:
        changed_path = next(
            (path for path in (coupling.file_a, coupling.file_b) if path in selected_paths), None
        )
        if changed_path is None:
            continue
        info = coupling_info_for(coupling, changed_path)
        if info.file == changed_path or info.rate_to_partner < parameters.coupling.min_ratio:
            continue
        item = CouplingEvidence(
            changed_path=changed_path,
            changed_path_role=classify_path_role(changed_path, path_role_rules),
            coupled_path=info.file,
            coupled_path_role=classify_path_role(info.file, path_role_rules),
            shared_revisions=info.shared_revisions,
            changed_path_revisions=info.file_revisions,
            coupled_path_revisions=info.coupled_file_revisions,
            coupling_ratio=info.ratio,
            changed_to_coupled_rate=info.rate_to_partner,
            ratio_lower_bound=coupling.ratio_lower_bound,
            coupled_path_is_changed=info.file in selected_paths,
        )
        key = (changed_path, info.file)
        current = evidence.get(key)
        if current is None or item.ratio_lower_bound > current.ratio_lower_bound:
            evidence[key] = item

    return sorted(
        evidence.values(),
        key=lambda item: (
            -item.ratio_lower_bound,
            -item.shared_revisions,
            -item.coupling_ratio,
            item.changed_path,
            item.coupled_path,
        ),
    )


def ci_failure_evidence(
    analysis: AnalysisResult,
    selected_paths: set[str],
) -> list[CIFailureEvidence]:
    evidence: list[CIFailureEvidence] = []
    for run in analysis.failed_ci_runs:
        matched_paths = sorted(set(run.implicated_paths) & selected_paths)
        if not matched_paths:
            continue
        evidence.append(
            CIFailureEvidence(
                run_id=run.run_id,
                workflow_name=run.workflow_name,
                run_url=run.run_url,
                commit_sha=run.commit_sha,
                conclusion=run.conclusion,
                created_at=run.created_at,
                implicated_changed_paths=matched_paths,
            )
        )
    return sorted(evidence, key=lambda item: (-item.created_at.timestamp(), -item.run_id))
