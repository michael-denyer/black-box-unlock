"""Deterministic presentation data for the standalone HTML report."""

from __future__ import annotations

from typing import Any

from black_box_unlock.core.models import AnalysisResult, TemporalCoupling


def _coupling_row(pair: TemporalCoupling, roles_by_path: dict[str, str]) -> dict[str, Any]:
    denominator = min(pair.commits_a, pair.commits_b)
    return {
        "key": f"{pair.file_a}\0{pair.file_b}",
        "file_a": pair.file_a,
        "file_b": pair.file_b,
        "role_a": roles_by_path[pair.file_a],
        "role_b": roles_by_path[pair.file_b],
        "shared_revisions": pair.co_change_count,
        "revisions_a": pair.commits_a,
        "revisions_b": pair.commits_b,
        "denominator": denominator,
        "raw_ratio": pair.coupling_ratio,
        "ratio_lower_bound": pair.ratio_lower_bound,
    }


def _coupling_sort_key(row: dict[str, Any]) -> tuple[float, int, float, str, str]:
    return (
        -row["ratio_lower_bound"],
        -row["shared_revisions"],
        -row["raw_ratio"],
        row["file_a"],
        row["file_b"],
    )


def build_report_payload(result: AnalysisResult) -> dict[str, Any]:
    """Return the complete analysis plus one confidence-enriched pair projection."""
    analysis = result.model_dump(mode="json")
    analysis["files"] = sorted(
        analysis["files"],
        key=lambda file: (-file["hotspot_score"], file["path"]),
    )
    roles_by_path = {file.path: file.path_role.value for file in result.files}
    couplings = sorted(
        (_coupling_row(pair, roles_by_path) for pair in result.couplings),
        key=_coupling_sort_key,
    )
    return {
        "schema_version": 2,
        "analysis": analysis,
        "couplings": couplings,
    }
