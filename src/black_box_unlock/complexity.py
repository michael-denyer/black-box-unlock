"""Indentation-based complexity proxy (Tornhill's whitespace method)."""

from collections.abc import Iterable
from pathlib import Path

TAB_SIZE = 4

# Serialized-data, generated, and asset files accumulate indentation by sheer
# size without representing code complexity. Scoring them like code makes a huge
# JSON seed or lockfile the "top hotspot"; treat their complexity as 0 so the
# hotspot ranking reflects code. The defect axis (bug-fix density) still flags
# them if they genuinely churn.
#
# Deliberately NOT here: config/markup (.yaml/.yml/.xml) — a churning Helm/k8s/CI
# manifest or API spec is a legitimate maintenance hotspot worth surfacing.
# Also not here: .ipynb — notebooks carry real code; their JSON envelope inflates
# the score (a known limitation pending cell-aware parsing), but zeroing them
# would hide genuine notebook hotspots, which is worse.
DATA_EXTENSIONS = frozenset(
    {
        ".json",
        ".jsonl",
        ".ndjson",
        ".geojson",
        ".csv",
        ".tsv",
        ".svg",
        ".lock",
        ".map",
    }
)
GENERATED_SUFFIXES = (".min.js", ".min.css")


def _is_data_or_generated(file_path: Path) -> bool:
    """True for serialized-data, config, lockfile, or minified/generated files."""
    name = file_path.name.lower()
    if name.endswith(GENERATED_SUFFIXES):
        return True
    return file_path.suffix.lower() in DATA_EXTENSIONS


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
    analysis window), for binary content (NUL bytes present — indentation
    measurement is meaningless), and for serialized-data/generated files
    (their indentation reflects file size, not code complexity).

    Args:
        file_path: Path to the file to measure.
        tab_size: Number of spaces a tab expands to.

    Returns:
        Sum of indentation levels across all non-blank lines.
    """
    if _is_data_or_generated(file_path):
        return 0.0

    try:
        text = file_path.read_text(errors="ignore")
    except OSError:
        return 0.0

    if "\x00" in text:
        return 0.0

    return indentation_complexity_lines(text.splitlines(), tab_size)
