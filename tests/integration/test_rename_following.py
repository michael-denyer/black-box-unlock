"""Real-Git checks that every history signal follows a file across git mv."""

import subprocess
from pathlib import Path

import pytest

from black_box_unlock.analysis import run_analysis
from black_box_unlock.core.models import CouplingPolicy
from black_box_unlock.git.xray import xray_file
from black_box_unlock.guard import coupling_warnings


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _commit(repo: Path, message: str, files: dict[str, str]) -> None:
    for name, content in files.items():
        (repo / name).write_text(content)
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", message)


def _module(value: int) -> str:
    return f"def alpha():\n    return {value}\n\n\ndef beta():\n    return {value}\n"


@pytest.fixture
def renamed_repo(tmp_path: Path) -> Path:
    """a.py gets five commits (two fixes) with partner.py, then becomes b.py and changes twice."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")
    messages = ["feat: add a", "feat: one", "fix: repair alpha", "feat: three", "fix: repair beta"]
    for value, message in enumerate(messages):
        _commit(repo, message, {"a.py": _module(value), "partner.py": f"CONFIG = {value}\n"})
    _git(repo, "mv", "a.py", "b.py")
    _git(repo, "commit", "-m", "refactor: rename a to b")
    for value in (5, 6):
        _commit(repo, f"feat: change {value}", {"b.py": _module(value)})
    return repo


def test_analysis_merges_history_from_before_the_rename(renamed_repo):
    result = run_analysis(renamed_repo, days=365, include_ci=False, xray_top=0)

    by_path = {file.path: file for file in result.files}
    assert set(by_path) == {"b.py", "partner.py"}
    renamed = by_path["b.py"]
    assert renamed.commits == 8
    assert renamed.bugfix_commits == 2
    assert renamed.renamed_from == ["a.py"]
    assert [(info.file, info.shared_revisions) for info in renamed.coupled_with] == [
        ("partner.py", 5)
    ]


def test_guard_warns_about_partners_from_before_the_rename(renamed_repo):
    warnings = coupling_warnings("b.py", renamed_repo, CouplingPolicy(min_ratio=0.5))

    assert len(warnings) == 1
    assert "co-changes with partner.py in 5 of its 8 revisions" in warnings[0]


def test_xray_counts_function_revisions_from_before_the_rename(renamed_repo):
    result = xray_file(renamed_repo, "b.py", days=365)

    assert {f.name: f.revisions for f in result.functions} == {"alpha": 7, "beta": 7}
    assert result.revisions_analyzed == 7


def test_xray_reads_the_parent_under_its_old_name_when_a_rename_also_edits(tmp_path):
    """Deleting gamma during the rename is attributed from a.py's spans, not beta's hunk header."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")
    kept = "".join(
        f"def {name}():\n" + "".join(f"    {name}_{n} = {n}\n" for n in range(8)) + "\n\n"
        for name in ("alpha", "beta")
    )
    _commit(repo, "add a", {"a.py": kept + "def gamma():\n    return 0\n"})
    _git(repo, "mv", "a.py", "b.py")
    (repo / "b.py").write_text(kept)
    _git(repo, "commit", "-am", "rename a to b and drop gamma")

    result = xray_file(repo, "b.py", days=365)

    assert result.revisions_analyzed == 2
    assert {f.name: f.revisions for f in result.functions} == {"alpha": 1, "beta": 1}


def test_xray_does_not_follow_a_reused_path_into_another_files_history(tmp_path: Path):
    """a.py becomes b.py, a new a.py appears, then a.py becomes c.py. c.py owns only its own two commits."""
    repo = tmp_path / "reuse"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")
    for value in range(3):
        _commit(repo, f"feat: old a {value}", {"a.py": _module(value)})
    _git(repo, "mv", "a.py", "b.py")
    _git(repo, "commit", "-m", "refactor: a to b")
    _commit(repo, "feat: new a", {"a.py": "def gamma():\n    return 1\n"})
    _commit(repo, "feat: new a again", {"a.py": "def gamma():\n    return 2\n"})
    _git(repo, "mv", "a.py", "c.py")
    _git(repo, "commit", "-m", "refactor: a to c")

    result = xray_file(repo, "c.py", days=365)

    assert result.revisions_analyzed == 2
    assert [(f.name, f.revisions) for f in result.functions] == [("gamma", 2)]
