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
    portable = json.loads((repo_root / "plugin.json").read_text())
    codex = json.loads((repo_root / ".codex-plugin" / "plugin.json").read_text())

    assert {
        project_version,
        __version__,
        installed_version("black-box-unlock"),
        plugin["version"],
        marketplace["plugins"][0]["version"],
        portable["version"],
        codex["version"],
    } == {project_version}


def test_codex_plugin_skills_mirror_the_claude_commands(repo_root):
    """Every Claude Code command and the forensics agent has a Codex skill of the same name."""
    commands = {p.stem for p in (repo_root / "commands").glob("*.md")}
    agents = {p.stem for p in (repo_root / "agents").glob("*.md")}
    skills = {p.name for p in (repo_root / "skills").iterdir() if (p / "SKILL.md").exists()}

    assert skills == commands | agents
    for name in skills:
        text = (repo_root / "skills" / name / "SKILL.md").read_text()
        assert text.startswith(f"---\nname: {name}\ndescription: ")
