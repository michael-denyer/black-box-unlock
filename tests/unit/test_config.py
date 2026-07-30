"""Tests for ``.bbu.toml`` parsing and profile resolution."""

import pytest

from black_box_unlock.config import (
    ReviewOverrides,
    load_project_config,
    resolve_review_settings,
)
from black_box_unlock.core.exceptions import ConfigurationError
from black_box_unlock.path_roles import PathRole


def test_missing_config_preserves_the_public_defaults(tmp_path):
    settings = resolve_review_settings(tmp_path)

    assert settings.parameters.model_dump() == {
        "days": 90,
        "min_coupling": 0.3,
        "min_shared_revisions": 2,
        "include_ci": False,
        "max_actions": 3,
        "profile": "default",
        "config_path": None,
    }
    assert settings.path_roles == ()


def test_default_profile_and_path_roles_are_loaded(tmp_path):
    (tmp_path / ".bbu.toml").write_text(
        """
default_profile = "release"

[[path_roles]]
pattern = "app/**/*.vue"
role = "source"

[profiles.release]
days = 180
min_shared_revisions = 3
include_ci = true
""".strip()
        + "\n"
    )

    settings = resolve_review_settings(tmp_path)

    assert settings.parameters.days == 180
    assert settings.parameters.min_coupling == 0.3
    assert settings.parameters.min_shared_revisions == 3
    assert settings.parameters.include_ci is True
    assert settings.parameters.profile == "release"
    assert settings.parameters.config_path == ".bbu.toml"
    assert settings.path_roles[0].role is PathRole.source


def test_explicit_overrides_win_over_the_named_profile(tmp_path):
    (tmp_path / ".bbu.toml").write_text(
        """
[profiles.release]
days = 180
include_ci = true
""".strip()
        + "\n"
    )

    settings = resolve_review_settings(
        tmp_path,
        profile_name="release",
        overrides=ReviewOverrides(days=30, include_ci=False),
    )

    assert settings.parameters.days == 30
    assert settings.parameters.include_ci is False


def test_unknown_profile_lists_available_names(tmp_path):
    (tmp_path / ".bbu.toml").write_text("[profiles.release]\ndays = 180\n")

    with pytest.raises(ConfigurationError, match="available profiles: release"):
        resolve_review_settings(tmp_path, profile_name="missing")


def test_invalid_toml_is_reported_as_configuration_error(tmp_path):
    (tmp_path / ".bbu.toml").write_text("[profiles.release\n")

    with pytest.raises(ConfigurationError, match=r"Invalid \.bbu\.toml"):
        load_project_config(tmp_path)


def test_unknown_keys_are_rejected(tmp_path):
    (tmp_path / ".bbu.toml").write_text("surprise = true\n")

    with pytest.raises(ConfigurationError, match="surprise"):
        load_project_config(tmp_path)


def test_profile_names_cannot_hide_whitespace(tmp_path):
    (tmp_path / ".bbu.toml").write_text('default_profile = " release "\n[profiles." release "]\n')

    with pytest.raises(ConfigurationError, match="padded with whitespace"):
        load_project_config(tmp_path)
