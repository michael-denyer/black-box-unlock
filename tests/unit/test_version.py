"""Keep every published version field on one value."""

import json
from importlib.metadata import version as installed_version

from black_box_unlock import __version__

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised by the Python 3.10 CI job
    import tomli as tomllib


def test_package_and_plugin_versions_match(repo_root):
    with (repo_root / "pyproject.toml").open("rb") as handle:
        project_version = tomllib.load(handle)["project"]["version"]
    plugin = json.loads((repo_root / ".claude-plugin" / "plugin.json").read_text())
    marketplace = json.loads((repo_root / ".claude-plugin" / "marketplace.json").read_text())

    assert {
        project_version,
        __version__,
        installed_version("black-box-unlock"),
        plugin["version"],
        marketplace["plugins"][0]["version"],
    } == {project_version}
