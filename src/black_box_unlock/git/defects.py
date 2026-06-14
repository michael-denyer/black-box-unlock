"""Bug-fix commit detection from commit messages.

Precision rule: conventional-commit prefixes docs/style/test/chore/ci/build/refactor
are excluded from defect classification — fixing a typo in docs is not a defect repair
in the Tornhill sense. Reverts are always counted regardless of what they revert.
"""

import re
from collections import Counter

from .log import Commit

REVERT_PATTERN = re.compile(r"\brevert\b", re.IGNORECASE)

NON_DEFECT_PREFIX = re.compile(
    r"^(docs|style|test|chore|ci|build|refactor)(\(.+?\))?:",
    re.IGNORECASE,
)

BUGFIX_PATTERN = re.compile(
    r"("
    r"\bfix(es|ed)?\b"
    r"|\bbug(fix)?\b"
    r"|\bhotfix\b"
    r"|\bdefect\b"
    r"|\bregression\b"
    r"|\bcorrect(ed|ing|ion)\b"
    r"|\bbroke(n)?\b"
    r"|\bcrash(es|ed|ing)?\b"
    r"|\brepair(s|ed|ing)?\b"
    r"|\bfault(y)?\b"
    r"|\bmalfunction(s|ed|ing)?\b"
    r")",
    re.IGNORECASE,
)


def is_bugfix_message(message: str) -> bool:
    """True when a commit message indicates a defect repair.

    Reverts always count. Conventional-commit prefixes docs/style/test/chore/ci/build/refactor
    are excluded even when the message contains bugfix keywords.
    """
    if REVERT_PATTERN.search(message):
        return True
    if NON_DEFECT_PREFIX.match(message):
        return False
    return bool(BUGFIX_PATTERN.search(message))


def bugfix_counts(commits: list[Commit]) -> dict[str, int]:
    """Count bug-fix commits per file path.

    Files repeatedly touched by fix commits are where defects live —
    this is the defect axis of Tornhill's hotspot validation.
    """
    counts: Counter[str] = Counter()
    for commit in commits:
        if not commit.message or not is_bugfix_message(commit.message):
            continue
        for file in commit.files:
            counts[file.path] += 1
    return dict(counts)
