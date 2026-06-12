"""Indentation-based complexity proxy (Tornhill's whitespace method)."""

from collections.abc import Iterable
from pathlib import Path

TAB_SIZE = 4


def indentation_complexity_lines(lines: Iterable[str], tab_size: int = TAB_SIZE) -> float:
    """Sum of logical indentation levels across non-blank lines.

    Cheap, language-agnostic complexity proxy: deeply nested code
    accumulates indentation.

    Args:
        lines: Source lines to measure (without trailing newlines).
        tab_size: Number of spaces a tab expands to.

    Returns:
        Sum of indentation levels across all non-blank lines.
    """
    total = 0
    for line in lines:
        if not line.strip():
            continue
        expanded = line.expandtabs(tab_size)
        total += (len(expanded) - len(expanded.lstrip(" "))) // tab_size
    return float(total)


def indentation_complexity(file_path: Path, tab_size: int = TAB_SIZE) -> float:
    """Sum of logical indentation levels across non-blank lines of a file.

    Returns 0.0 for missing or unreadable files (e.g. deleted within the
    analysis window), and 0.0 for binary content (NUL bytes present —
    indentation measurement is meaningless).

    Args:
        file_path: Path to the file to measure.
        tab_size: Number of spaces a tab expands to.

    Returns:
        Sum of indentation levels across all non-blank lines.
    """
    try:
        text = file_path.read_text(errors="ignore")
    except OSError:
        return 0.0

    if "\x00" in text:
        return 0.0

    return indentation_complexity_lines(text.splitlines(), tab_size)
