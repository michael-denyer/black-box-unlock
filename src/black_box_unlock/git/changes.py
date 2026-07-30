"""Typed selection of committed and local Git changes."""

import subprocess
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from ..core.exceptions import ChangeSelectionError, InvalidRevisionError
from .run import run_git


class ChangeKind(str, Enum):
    """Structural status of one selected path."""

    added = "added"
    modified = "modified"
    deleted = "deleted"
    renamed = "renamed"
    copied = "copied"
    type_changed = "type_changed"
    untracked = "untracked"


class BaseChange(BaseModel):
    """Branch and local work compared with an upstream merge base."""

    kind: Literal["base"] = "base"
    base_ref: str = Field(default="origin/main", min_length=1)


class StagedChange(BaseModel):
    """Index contents compared with HEAD."""

    kind: Literal["staged"] = "staged"


class WorkingTreeChange(BaseModel):
    """Unstaged tracked files and untracked files."""

    kind: Literal["working_tree"] = "working_tree"


ChangeSelector = Annotated[
    BaseChange | StagedChange | WorkingTreeChange,
    Field(discriminator="kind"),
]


class ChangedPath(BaseModel):
    """One path in a selected change."""

    path: str = Field(min_length=1)
    kind: ChangeKind
    previous_path: str | None = None

    @model_validator(mode="after")
    def rename_has_previous_path(self) -> "ChangedPath":
        moved = self.kind in {ChangeKind.renamed, ChangeKind.copied}
        if moved != (self.previous_path is not None):
            raise ValueError("renamed and copied paths must include previous_path")
        return self


class BaseProvenance(BaseModel):
    """Resolved merge-base state for branch and local review."""

    kind: Literal["base"] = "base"
    head_oid: str
    requested_base: str
    resolved_base_oid: str
    merge_base_oid: str
    layers: tuple[
        Literal["committed"],
        Literal["staged"],
        Literal["unstaged"],
        Literal["untracked"],
    ] = (
        "committed",
        "staged",
        "unstaged",
        "untracked",
    )
    observed_at: datetime
    cache_used: Literal[False] = False


class StagedProvenance(BaseModel):
    """Resolved state for index-only review."""

    kind: Literal["staged"] = "staged"
    head_oid: str | None
    layers: tuple[Literal["staged"]] = ("staged",)
    observed_at: datetime
    cache_used: Literal[False] = False


class WorkingTreeProvenance(BaseModel):
    """Resolved state for unstaged and untracked review."""

    kind: Literal["working_tree"] = "working_tree"
    head_oid: str | None
    layers: tuple[Literal["unstaged"], Literal["untracked"]] = (
        "unstaged",
        "untracked",
    )
    observed_at: datetime
    cache_used: Literal[False] = False


ChangeProvenance = Annotated[
    BaseProvenance | StagedProvenance | WorkingTreeProvenance,
    Field(discriminator="kind"),
]


class ChangeSet(BaseModel):
    """Typed paths and provenance for exactly one selector."""

    selector: ChangeSelector
    provenance: ChangeProvenance
    paths: list[ChangedPath]

    @model_validator(mode="after")
    def selector_matches_provenance_and_paths_are_unique(self) -> "ChangeSet":
        if self.selector.kind != self.provenance.kind:
            raise ValueError("change selector and provenance kinds must match")
        path_names = [path.path for path in self.paths]
        if len(path_names) != len(set(path_names)):
            raise ValueError("change paths must be unique")
        return self


def _resolve_ref(repo_path: Path, ref: str) -> str:
    try:
        return run_git(repo_path, ["rev-parse", "--verify", f"{ref}^{{commit}}"]).strip()
    except subprocess.CalledProcessError as error:
        raise InvalidRevisionError(f"Cannot resolve Git revision: {ref}") from error


def _resolve_optional_head(repo_path: Path) -> str | None:
    """Resolve HEAD, returning None for a repository without commits."""
    try:
        return run_git(
            repo_path,
            ["rev-parse", "--verify", "HEAD^{commit}"],
        ).strip()
    except subprocess.CalledProcessError:
        return None


def parse_name_status_z(output: str) -> list[ChangedPath]:
    """Parse ``git diff --name-status -z`` without corrupting unusual paths."""
    fields = output.split("\0")
    if fields and fields[-1] == "":
        fields.pop()

    changes: list[ChangedPath] = []
    index = 0
    while index < len(fields):
        status = fields[index]
        index += 1
        code = status[:1]
        if code in {"R", "C"}:
            if index + 1 >= len(fields):
                raise ChangeSelectionError("Malformed Git rename/copy record")
            previous_path, path = fields[index], fields[index + 1]
            index += 2
            changes.append(
                ChangedPath(
                    path=path,
                    previous_path=previous_path,
                    kind=ChangeKind.renamed if code == "R" else ChangeKind.copied,
                )
            )
            continue
        if index >= len(fields):
            raise ChangeSelectionError("Malformed Git name-status record")
        path = fields[index]
        index += 1
        kinds = {
            "A": ChangeKind.added,
            "M": ChangeKind.modified,
            "D": ChangeKind.deleted,
            "T": ChangeKind.type_changed,
        }
        if code == "U":
            raise ChangeSelectionError(f"Cannot review an unresolved merge conflict: {path}")
        try:
            kind = kinds[code]
        except KeyError as error:
            raise ChangeSelectionError(f"Unsupported Git change status: {status}") from error
        changes.append(ChangedPath(path=path, kind=kind))
    return changes


def _untracked_paths(repo_path: Path) -> list[ChangedPath]:
    output = run_git(
        repo_path,
        ["ls-files", "--others", "--exclude-standard", "-z"],
    )
    return [
        ChangedPath(path=path, kind=ChangeKind.untracked) for path in output.split("\0") if path
    ]


def _deduplicate(changes: list[ChangedPath]) -> list[ChangedPath]:
    """Return one deterministic record per current path."""
    by_path: dict[str, ChangedPath] = {}
    for change in changes:
        existing = by_path.get(change.path)
        if existing is None or existing.kind is ChangeKind.untracked:
            by_path[change.path] = change
    return sorted(by_path.values(), key=lambda change: change.path)


def collect_change_set(repo_path: Path, selector: ChangeSelector) -> ChangeSet:
    """Resolve one selector and collect its repository-relative paths."""
    observed_at = datetime.now(timezone.utc)

    if isinstance(selector, BaseChange):
        base_oid = _resolve_ref(repo_path, selector.base_ref)
        head_oid = _resolve_ref(repo_path, "HEAD")
        try:
            merge_base_oid = run_git(
                repo_path,
                ["merge-base", base_oid, head_oid],
            ).strip()
        except subprocess.CalledProcessError as error:
            raise ChangeSelectionError(
                f"No merge base between {selector.base_ref} and HEAD"
            ) from error
        tracked = parse_name_status_z(
            run_git(
                repo_path,
                ["diff", "--name-status", "-z", "--find-renames", merge_base_oid],
            )
        )
        paths = _deduplicate([*tracked, *_untracked_paths(repo_path)])
        provenance = BaseProvenance(
            head_oid=head_oid,
            requested_base=selector.base_ref,
            resolved_base_oid=base_oid,
            merge_base_oid=merge_base_oid,
            observed_at=observed_at,
        )
    elif isinstance(selector, StagedChange):
        head_oid = _resolve_optional_head(repo_path)
        diff_args = ["diff", "--cached", "--name-status", "-z", "--find-renames"]
        if head_oid is not None:
            diff_args.append("HEAD")
        paths = _deduplicate(parse_name_status_z(run_git(repo_path, diff_args)))
        provenance = StagedProvenance(
            head_oid=head_oid,
            observed_at=observed_at,
        )
    else:
        head_oid = _resolve_optional_head(repo_path)
        tracked = parse_name_status_z(
            run_git(
                repo_path,
                ["diff", "--name-status", "-z", "--find-renames"],
            )
        )
        paths = _deduplicate([*tracked, *_untracked_paths(repo_path)])
        provenance = WorkingTreeProvenance(
            head_oid=head_oid,
            observed_at=observed_at,
        )

    return ChangeSet(selector=selector, provenance=provenance, paths=paths)
