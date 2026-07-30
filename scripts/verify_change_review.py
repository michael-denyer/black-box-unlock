"""Deterministic release proof for the v1.3 change-review contract."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from black_box_unlock import mcp_server


def _git(repo: Path, *args: str) -> None:
    environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Release Proof",
        "GIT_AUTHOR_EMAIL": "proof@example.com",
        "GIT_COMMITTER_NAME": "Release Proof",
        "GIT_COMMITTER_EMAIL": "proof@example.com",
    }
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env=environment,
    )


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", message)


def _build_repository(repo: Path) -> None:
    _git(repo, "init")
    source = repo / "src" / "a.py"
    companion = repo / "tests" / "test_a.py"
    source.parent.mkdir()
    companion.parent.mkdir()
    for revision in range(11):
        source.write_text(f"value = {revision}\n")
        companion.write_text(f"expected = {revision}\n")
        _commit(repo, f"coupled {revision}")
    for revision in range(2):
        source.write_text(f"value = {revision + 20}\n")
        _commit(repo, f"source only {revision}")
    for revision in range(2):
        companion.write_text(f"expected = {revision + 20}\n")
        _commit(repo, f"test only {revision}")
    one = repo / "src" / "one.py"
    one_test = repo / "tests" / "test_one.py"
    one.write_text("one = 1\n")
    one_test.write_text("one = 1\n")
    _commit(repo, "one-off pair")
    source.write_text("value = 99\n")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="bbu-review-proof-") as temporary:
        repo = Path(temporary)
        _build_repository(repo)
        command = [
            sys.executable,
            "-m",
            "black_box_unlock.cli",
            "review-change",
            "--working-tree",
            "--repo",
            str(repo),
        ]
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        cli_result = json.loads(completed.stdout)
        mcp_result = mcp_server.review_change(
            repo_path=str(repo),
            mode="working_tree",
        )

    actions = cli_result["actions"]
    assert len(actions) <= 3
    assert actions == mcp_result["actions"]
    coupling = actions[0]["evidence"][0]
    assert coupling["coupled_path"] == "tests/test_a.py"
    assert coupling["shared_revisions"] == 11
    assert coupling["changed_path_revisions"] == 13
    assert coupling["confidence_lower_bound"] > 0.5
    print("change-review release proof passed")


if __name__ == "__main__":
    main()
