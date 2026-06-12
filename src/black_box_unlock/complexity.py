"""Indentation-based complexity proxy (Tornhill's whitespace method)."""

from pathlib import Path

TAB_SIZE = 4


def indentation_complexity(file_path: Path, tab_size: int = TAB_SIZE) -> float:
    """Sum of logical indentation levels across non-blank lines.

    Cheap, language-agnostic complexity proxy: deeply nested code
    accumulates indentation. Returns 0.0 for missing or unreadable files
    (e.g. deleted within the analysis window).

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

    total = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        expanded = line.expandtabs(tab_size)
        total += (len(expanded) - len(expanded.lstrip(" "))) // tab_size
    return float(total)
