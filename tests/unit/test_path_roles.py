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
