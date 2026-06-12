"""Bug-fix commit detection from commit messages.

Precision rule: conventional-commit prefixes docs/style/test/chore/ci/build/refactor
are excluded from defect classification — fixing a typo in docs is not a defect repair
in the Tornhill sense. Reverts are always counted regardless of what they revert.
"""

import re
from collections import Counter
from typing import Any

REVERT_PATTERN = re.compile(r"\brevert\b", re.IGNORECASE)

NON_DEFECT_PREFIX = re.compile(
    r"^(docs|style|test|chore|ci|build|refactor)(\(.+?\))?:",
    re.IGNORECASE,
)

BUGFIX_PATTERN = re.compile(
    r"(\bfix(es|ed)?\b|\bbug(fix)?\b|\bhotfix\b|\bdefect\b|\bregression\b)",
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


def bugfix_counts(history: dict[str, Any]) -> dict[str, int]:
    """Count bug-fix commits per file path.

    Files repeatedly touched by fix commits are where defects live —
    this is the defect axis of Tornhill's hotspot validation.

    Args:
        history: Git history dict with an 'entries' list, each entry having
            a 'message' key and a 'files' list of dicts with 'path'.

    Returns:
        Dict mapping file path to number of bug-fix commits touching it.
    """
    counts: Counter[str] = Counter()
    for entry in history.get("entries", []):
        message = entry.get("message")
        if not message or not is_bugfix_message(message):
            continue
        for file_info in entry.get("files", []):
            counts[file_info["path"]] += 1
    return dict(counts)
