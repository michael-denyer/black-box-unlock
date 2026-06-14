"""Treemap data transformation for Plotly.js visualization."""

from black_box_unlock.core.models import FileForensics


def build_treemap_data(files: list[FileForensics]) -> dict:  # [5b] Plotly treemap format
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

    used_ids: set[str] = {""}
    dir_id_by_path: dict[str, str] = {}  # dir path -> the unique id assigned to its node

    def unique_id(desired: str) -> str:
        """A globally unique id. Plotly's treemap renders nothing if any id repeats,
        which happens when a path is both a file and a directory across history."""
        if desired not in used_ids:
            used_ids.add(desired)
            return desired
        n = 2
        while f"{desired}#{n}" in used_ids:
            n += 1
        collision_free = f"{desired}#{n}"
        used_ids.add(collision_free)
        return collision_free

    for file in files:
        parts = file.path.split("/")

        # Build directory hierarchy (full path keys the node; id may be disambiguated)
        current_parent_id = ""  # Start from root (empty string id)
        for i, part in enumerate(parts[:-1]):  # All but last (which is the file)
            dir_path = "/".join(parts[: i + 1])

            if dir_path not in dir_id_by_path:
                node_id = unique_id(dir_path)
                dir_id_by_path[dir_path] = node_id
                ids.append(node_id)
                labels.append(part)
                parents.append(current_parent_id)
                values.append(0)
                colors.append(0)
                hovertext.append(dir_path)

            current_parent_id = dir_id_by_path[dir_path]

        # Add the file (its id may collide with a same-named directory node)
        ids.append(unique_id(file.path))
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
