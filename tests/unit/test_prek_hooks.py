"""Check that the maid prek hook validates every file prek passes to it."""

import os
import re
import shlex
import subprocess

import pytest

# The real maid validates its first file argument and ignores the rest.
FIRST_ARGUMENT_ONLY_MAID = """#!/bin/sh
case "$(cat "$1")" in *BROKEN*) exit 1 ;; esac
"""


# prek.toml spreads inline tables over several lines, which is TOML 1.1 syntax
# that tomllib and tomli reject, so the entry is read with a pattern.
MAID_ENTRY = re.compile(r'id = "maid",[^}]*?entry = (?:"""(.*?)"""|"(.*?)")', re.DOTALL)


def _maid_entry(repo_root):
    match = MAID_ENTRY.search((repo_root / "prek.toml").read_text())
    assert match, "prek.toml has no maid hook entry"
    return match.group(1) or match.group(2)


@pytest.mark.parametrize(
    ("contents", "expected_failure"),
    [
        (["valid", "valid"], False),
        (["BROKEN", "valid"], True),
        (["valid", "BROKEN"], True),
        (["valid", "valid", "BROKEN"], True),
    ],
)
def test_maid_hook_fails_when_any_file_is_broken(repo_root, tmp_path, contents, expected_failure):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    maid = bin_dir / "maid"
    maid.write_text(FIRST_ARGUMENT_ONLY_MAID)
    maid.chmod(0o755)
    files = []
    for index, content in enumerate(contents):
        path = tmp_path / f"doc{index}.md"
        path.write_text(content)
        files.append(str(path))

    result = subprocess.run(
        [*shlex.split(_maid_entry(repo_root)), *files],
        env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
        check=False,
    )

    assert (result.returncode != 0) == expected_failure
