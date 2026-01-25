"""Coupling graph data transformation for Cytoscape.js visualization."""

from black_box_unlock.core.models import FileForensics


def _get_directory(path: str) -> str:
    """Extract top-level directory from path.

    Args:
        path: File path like "src/auth.py" or "README.md"

    Returns:
        Top-level directory or "root" for root-level files.
    """
    if "/" not in path:
        return "root"
    return path.split("/")[0]


def _make_node(path: str, churn: int) -> dict:
    """Create a Cytoscape.js node for a file.

    Args:
        path: File path.
        churn: Hotspot score (0 for external nodes).

    Returns:
        Cytoscape.js node dict with data fields.
    """
    return {
        "data": {
            "id": path,
            "label": path.split("/")[-1],
            "churn": churn,
            "directory": _get_directory(path),
        }
    }


def build_coupling_graph_data(files: list[FileForensics]) -> dict:
    """Transform file forensics to Cytoscape.js graph format.

    Args:
        files: List of FileForensics with coupling information.

    Returns:
        Dict with nodes, edges, directories, and maxChurn for Cytoscape.js.
    """
    if not files:
        return {"nodes": [], "edges": [], "directories": [], "maxChurn": 0}

    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    seen_edges: set[tuple[str, str]] = set()
    directories: set[str] = set()

    for file in files:
        node = _make_node(file.path, file.hotspot_score)
        nodes[file.path] = node
        directories.add(node["data"]["directory"])

        for coupling in file.coupled_with:
            target = coupling.file
            source = file.path

            edge_key = tuple(sorted([source, target]))
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)

            source_dir = _get_directory(source)
            target_dir = _get_directory(target)

            edges.append(
                {
                    "data": {
                        "source": source,
                        "target": target,
                        "coupling": coupling.ratio,
                        "crossModule": source_dir != target_dir,
                    }
                }
            )

            if target not in nodes:
                target_node = _make_node(target, churn=0)
                nodes[target] = target_node
                directories.add(target_node["data"]["directory"])

    max_churn = max((n["data"]["churn"] for n in nodes.values()), default=0)

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "directories": sorted(directories),
        "maxChurn": max_churn,
    }
