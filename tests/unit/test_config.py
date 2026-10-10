"""Tests for ``.bbu.toml`` parsing and profile resolution."""

import pytest

from black_box_unlock.config import load_project_config, resolve_coupling_policy
from black_box_unlock.core.exceptions import ConfigurationError
from black_box_unlock.core.models import CouplingPolicy
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


def test_coupling_table_sets_the_policy_and_overrides_win(tmp_path):
    (tmp_path / ".bbu.toml").write_text(
        "[coupling]\nmin_ratio = 0.5\nmax_changeset_size = 80\nrequire_live_partner = false\n"
    )

    policy = resolve_coupling_policy(tmp_path, min_shared_revisions=3, max_changeset_size=None)

    assert policy == CouplingPolicy(
        min_ratio=0.5,
        min_shared_revisions=3,
        max_changeset_size=80,
        require_live_partner=False,
    )


def test_missing_coupling_table_uses_the_policy_defaults(tmp_path):
    assert resolve_coupling_policy(tmp_path) == CouplingPolicy()


@pytest.mark.parametrize(
    "table",
    [
        "[coupling]\nmin_ratio = 1.5\n",
        "[coupling]\nmax_changeset_size = 1\n",
        "[coupling]\nfloor = 2\n",
    ],
)
def test_invalid_coupling_table_is_a_configuration_error(tmp_path, table):
    (tmp_path / ".bbu.toml").write_text(table)

    with pytest.raises(ConfigurationError):
        resolve_coupling_policy(tmp_path)


def test_invalid_coupling_override_is_a_configuration_error(tmp_path):
    with pytest.raises(ConfigurationError, match="Invalid coupling policy"):
        resolve_coupling_policy(tmp_path, max_changeset_size=1)


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
