"""Tests for project and built-in path-role classification."""

import pytest
from pydantic import ValidationError

from black_box_unlock.path_roles import (
    PathRole,
    PathRoleRule,
    classify_path_role,
)


def test_double_star_matches_zero_or_many_directories():
    rule = PathRoleRule(pattern="app/**/*.rb", role=PathRole.source)

    assert rule.matches("app/model.rb") is True
    assert rule.matches("app/models/user.rb") is True
    assert rule.matches("other/model.rb") is False


def test_pattern_without_a_directory_matches_any_basename():
    rule = PathRoleRule(pattern="*.snap", role=PathRole.generated)

    assert rule.matches("view.snap") is True
    assert rule.matches("tests/fixtures/view.snap") is True


def test_trailing_slash_matches_everything_below_a_directory():
    rule = PathRoleRule(pattern="vendor/", role=PathRole.generated)

    assert rule.matches("vendor/library/file.py") is True
    assert rule.matches("vendorized/file.py") is False


def test_project_rules_are_first_match_wins_before_builtins():
    rules = (
        PathRoleRule(pattern="docs/generated/**", role=PathRole.generated),
        PathRoleRule(pattern="docs/**", role=PathRole.source),
    )

    generated = classify_path_role("docs/generated/schema.md", rules)
    source = classify_path_role("docs/guide.md", rules)

    assert generated.model_dump() == {
        "role": PathRole.generated,
        "rule": "project:docs/generated/**",
    }
    assert source.model_dump() == {
        "role": PathRole.source,
        "rule": "project:docs/**",
    }


@pytest.mark.parametrize(
    "path",
    [
        "web/index.html",
        "web/app.css",
        "web/theme.scss",
        "scripts/release.sh",
        "db/schema.sql",
        "web/App.vue",
    ],
)
def test_product_assets_are_source_files(path):
    assert classify_path_role(path).role is PathRole.source


@pytest.mark.parametrize("pattern", ["", "/absolute/**", "../outside/**", "file[0-9].py"])
def test_invalid_or_unsupported_patterns_fail_at_the_config_boundary(pattern):
    with pytest.raises(ValidationError):
        PathRoleRule(pattern=pattern, role=PathRole.source)


@pytest.mark.parametrize(
    "path",
    [
        "pkg/foo_test.go",
        "web/Foo.test.tsx",
        "web/foo.spec.ts",
        "web/foo.spec.js",
        "web/foo.test.js",
        "src/main/FooTest.java",
        "src/main/FooTests.kt",
        "src/FooSpec.scala",
        "src/FooTests.cs",
        "lib/foo_test.py",
        "lib/test_foo.py",
        "lib/conftest.py",
        "conftest.py",
        "app/foo_spec.rb",
        "src/foo_test.rs",
        "web/__tests__/foo.js",
        "src/test/java/Foo.java",
    ],
)
def test_test_conventions_outside_a_tests_directory_are_test(path):
    assert classify_path_role(path).role is PathRole.test


@pytest.mark.parametrize(
    "path",
    [
        "src/contest.py",
        "src/latest.py",
        "src/protest/runner.py",
        "src/Latest.java",
        "src/Contest.java",
        "src/attest.go",
        "src/testing.py",
    ],
)
def test_names_that_merely_contain_test_are_not_test(path):
    assert classify_path_role(path).role is not PathRole.test


@pytest.mark.parametrize(
    ("path", "role"),
    [
        ("docs/how_to_test.md", PathRole.docs),
        ("docs/api.spec.md", PathRole.docs),
        (".github/workflows/unit_test.yml", PathRole.config),
        ("config/load_test.toml", PathRole.config),
        ("migrations/0001_test.sql", PathRole.migration),
        ("vendor/x/foo_test.go", PathRole.generated),
        ("node_modules/a/b.spec.js", PathRole.generated),
    ],
)
def test_test_suffix_does_not_override_docs_config_migration_or_generated(path, role):
    assert classify_path_role(path).role is role


@pytest.mark.parametrize(
    ("path", "role"),
    [
        ("src/hooks/useThing.ts", PathRole.source),
        ("web/src/hooks/useThing.tsx", PathRole.source),
        ("hooks/guard.sh", PathRole.config),
        (".githooks/pre-commit", PathRole.config),
        (".github/workflows/ci.yml", PathRole.config),
        ("packages/app/.github/note.txt", PathRole.other),
        ("docs/guide.html", PathRole.docs),
        ("src/docs/render.py", PathRole.source),
        ("src/config/loader.py", PathRole.source),
        ("config/settings.py", PathRole.config),
        (".claude-plugin/plugin.json", PathRole.config),
    ],
)
def test_directory_rules_apply_only_at_the_repository_root(path, role):
    assert classify_path_role(path).role is role
