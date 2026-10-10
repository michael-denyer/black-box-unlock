"""Tests for ``.bbu.toml`` parsing and profile resolution."""

import pytest

from black_box_unlock.config import load_project_config
from black_box_unlock.core.exceptions import ConfigurationError
from black_box_unlock.path_roles import PathRole


def test_missing_config_returns_an_empty_project_config(tmp_path):
    config = load_project_config(tmp_path)

    assert config.default_profile is None
    assert config.profiles == {}
    assert config.path_roles == ()


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

    config = load_project_config(tmp_path)

    assert config.default_profile == "release"
    assert config.profiles["release"].days == 180
    assert config.profiles["release"].min_shared_revisions == 3
    assert config.profiles["release"].include_ci is True
    assert config.path_roles[0].role is PathRole.source


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
