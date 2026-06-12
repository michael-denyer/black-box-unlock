"""File ownership calculation from git history."""

from collections import defaultdict

from ..core.models import FileOwnership

# Type alias for git history JSON structure
GitHistoryData = dict


def parse_ownership_from_history(
    history: GitHistoryData,
) -> list[FileOwnership]:  # [3c] Parse authors per file
    """Parse git history entries into FileOwnership models.

    Aggregates unique authors and commit counts per file across all entries.

    Args:
        history: Parsed git history dict with "entries" list.

    Returns:
        List of FileOwnership models, one per unique file path.
    """
    file_authors: dict[str, set[str]] = defaultdict(set)
    file_commits: dict[str, int] = defaultdict(int)

    for entry in history.get("entries", []):
        author = entry.get("author_email", "").strip()
        if not author:
            author = "unknown"

        for file_info in entry.get("files", []):
            path = file_info["path"]
            file_authors[path].add(author)
            file_commits[path] += 1

    return [
        FileOwnership(
            path=path,
            authors=sorted(authors),
            commits=file_commits[path],
        )
        for path, authors in file_authors.items()
    ]


# Backward compatibility aliases
parse_ownership_from_gmap = parse_ownership_from_history
calculate_file_ownership = parse_ownership_from_history
