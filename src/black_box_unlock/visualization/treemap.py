"""Treemap data transformation for Plotly.js visualization."""

from black_box_unlock.core.models import FileForensics


def build_treemap_data(files: list[FileForensics]) -> dict:
    """Transform flat file list to Plotly treemap hierarchical format.

    Args:
        files: List of FileForensics with path, lines_changed, hotspot_score.

    Returns:
        Dict with ids, labels, parents, values, colors, hovertext arrays for Plotly.
        Uses full paths as ids to handle duplicate directory names.
    """
    ids: list[str] = [""]  # Root id
    labels: list[str] = [""]  # Root label (display name)
    parents: list[str] = [""]  # Root has no parent
    values: list[int] = [0]  # Root value
    colors: list[int] = [0]  # Root color
    hovertext: list[str] = [""]  # Root has no hover

    # Track directories we've already added
    seen_dirs: set[str] = set()

    for file in files:
        parts = file.path.split("/")

        # Build directory hierarchy
        current_parent_id = ""  # Start from root (empty string id)
        for i, part in enumerate(parts[:-1]):  # All but last (which is the file)
            # Build the full path to this directory for uniqueness
            dir_path = "/".join(parts[: i + 1])

            if dir_path not in seen_dirs:
                seen_dirs.add(dir_path)
                ids.append(dir_path)
                labels.append(part)
                parents.append(current_parent_id)
                values.append(0)
                colors.append(0)
                hovertext.append(dir_path)

            # Update parent id for next level - use full path
            current_parent_id = dir_path

        # Add the file
        ids.append(file.path)
        labels.append(parts[-1])
        parents.append(current_parent_id)
        values.append(file.lines_changed)
        colors.append(file.hotspot_score)
        hover_text = (
            f"{file.path}<br>"
            f"Lines: {file.lines_changed:,}<br>"
            f"Hotspot: {file.hotspot_score:,}<br>"
            f"Commits: {file.commits}"
        )
        hovertext.append(hover_text)

    return {
        "ids": ids,
        "labels": labels,
        "parents": parents,
        "values": values,
        "colors": colors,
        "hovertext": hovertext,
    }
