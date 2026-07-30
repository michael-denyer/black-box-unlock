"""Explainable repository path-role classification."""

import re
from enum import Enum
from functools import lru_cache
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, field_validator


class PathRole(str, Enum):
    """Stable, coarse role of a repository path."""

    source = "source"
    test = "test"
    docs = "docs"
    config = "config"
    migration = "migration"
    generated = "generated"
    other = "other"


class PathRoleRule(BaseModel):
    """One project rule. Rules are evaluated in file order."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pattern: str
    role: PathRole

    @field_validator("pattern")
    @classmethod
    def pattern_is_repo_relative(cls, value: str) -> str:
        pattern = value.strip()
        if not pattern:
            raise ValueError("path-role pattern must not be empty")
        if pattern.startswith("/") or "\\" in pattern:
            raise ValueError("path-role pattern must be a POSIX repository-relative glob")
        if ".." in PurePosixPath(pattern).parts:
            raise ValueError("path-role pattern must not traverse outside the repository")
        if "[" in pattern or "]" in pattern:
            raise ValueError("path-role patterns support *, **, and ? but not character classes")
        return pattern

    def matches(self, path: str) -> bool:
        """Return whether this rule matches one Git-style repository path."""
        return _compile_path_glob(self.pattern).fullmatch(path) is not None


class PathRoleClassification(BaseModel):
    """A role plus the rule that selected it."""

    role: PathRole
    rule: str


@lru_cache(maxsize=256)
def _compile_path_glob(pattern: str) -> re.Pattern[str]:
    """Compile a small, path-aware glob.

    ``*`` and ``?`` stay within a path segment. ``**`` crosses directories,
    and ``**/`` also matches zero directories.
    """
    normalized = pattern.rstrip("/")
    if pattern.endswith("/"):
        normalized += "/**"

    expression: list[str] = []
    index = 0
    while index < len(normalized):
        character = normalized[index]
        if character == "*":
            if index + 1 < len(normalized) and normalized[index + 1] == "*":
                index += 2
                if index < len(normalized) and normalized[index] == "/":
                    expression.append("(?:.*/)?")
                    index += 1
                else:
                    expression.append(".*")
                continue
            expression.append("[^/]*")
        elif character == "?":
            expression.append("[^/]")
        else:
            expression.append(re.escape(character))
        index += 1

    body = "".join(expression)
    if "/" not in normalized:
        body = rf"(?:.*/)?{body}"
    return re.compile(body)


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


def classify_path_role(
    path: str,
    project_rules: tuple[PathRoleRule, ...] = (),
) -> PathRoleClassification:
    """Classify a path with project rules first, then fixed built-ins."""
    for rule in project_rules:
        if rule.matches(path):
            return PathRoleClassification(role=rule.role, rule=f"project:{rule.pattern}")

    candidate = PurePosixPath(path)
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
