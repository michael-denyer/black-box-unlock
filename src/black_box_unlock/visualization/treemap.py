"""Treemap data transformation for Plotly.js visualization."""

from black_box_unlock.core.models import FileForensics


def build_treemap_data(files: list[FileForensics]) -> dict:
    """Transform flat file list to Plotly treemap hierarchical format.

    Args:
        files: List of FileForensics with path, lines_changed, hotspot_score.

    Returns:
        Dict with labels, parents, values, colors, customdata arrays for Plotly.
    """
    labels: list[str] = [""]  # Root node
    parents: list[str] = [""]  # Root has no parent
    values: list[int] = [0]  # Root value
    colors: list[int] = [0]  # Root color
    hovertext: list[str] = [""]  # Root has no hover

    # Track directories we've already added
    seen_dirs: set[str] = set()

    for file in files:
        parts = file.path.split("/")

        # Build directory hierarchy
        current_parent = ""  # Start from root
        for i, part in enumerate(parts[:-1]):  # All but last (which is the file)
            # Build the full path to this directory for uniqueness
            dir_path = "/".join(parts[: i + 1])

            if dir_path not in seen_dirs:
                seen_dirs.add(dir_path)
                labels.append(part)
                parents.append(current_parent if current_parent else "")
                values.append(0)  # Directories have 0 value
                colors.append(0)  # Directories have 0 color
                hovertext.append(dir_path)

            # Update parent for next level - use just the directory name
            current_parent = part

        # Add the file itself
        filename = parts[-1]
        labels.append(filename)
        parents.append(current_parent if current_parent else "")
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
        "labels": labels,
        "parents": parents,
        "values": values,
        "colors": colors,
        "hovertext": hovertext,
    }
