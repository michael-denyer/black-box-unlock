"""Bug-fix commit detection from commit messages."""

import re
from collections import Counter
from typing import Any

BUGFIX_PATTERN = re.compile(
    r"(\bfix(es|ed)?\b|\bbug(fix)?\b|\bhotfix\b|\bdefect\b|\brevert\b|\bregression\b)",
    re.IGNORECASE,
)


def is_bugfix_message(message: str) -> bool:
    """True when a commit message indicates a defect repair."""
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
