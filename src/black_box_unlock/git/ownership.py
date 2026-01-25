"""File ownership calculation from git history."""

from collections import defaultdict

from ..core.models import FileOwnership

# Type alias for gmap JSON structure
GmapData = dict


def parse_ownership_from_gmap(gmap_data: GmapData) -> list[FileOwnership]:
    """Parse gmap JSON output into FileOwnership models.

    Aggregates unique authors and commit counts per file across all entries.

    Args:
        gmap_data: Parsed JSON from gmap export --json.

    Returns:
        List of FileOwnership models, one per unique file path.
    """
    file_authors: dict[str, set[str]] = defaultdict(set)
    file_commits: dict[str, int] = defaultdict(int)

    for entry in gmap_data.get("entries", []):
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


# Backward compatibility alias
calculate_file_ownership = parse_ownership_from_gmap
