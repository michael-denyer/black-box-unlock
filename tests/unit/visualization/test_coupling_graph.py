"""Unit tests for coupling graph data transformation."""

from black_box_unlock.core.models import CouplingInfo, FileForensics
from black_box_unlock.visualization.coupling_graph import build_coupling_graph_data


class TestBuildCouplingGraphData:
    """Tests for build_coupling_graph_data function."""

    def test_empty_files_returns_empty_graph(self):
        """Empty file list returns empty nodes and edges."""
        result = build_coupling_graph_data([])

        assert result["nodes"] == []
        assert result["edges"] == []
        assert result["directories"] == []
        assert result["maxChurn"] == 0
        assert result["totalEdges"] == 0

    def test_files_without_coupling_returns_nodes_only(self):
        """Files with no coupling create nodes but no edges."""
        files = [
            FileForensics(
                path="src/auth.py",
                commits=10,
                lines_changed=200,
                authors=["alice@example.com"],
                coupled_with=[],
            )
        ]

        result = build_coupling_graph_data(files)

        assert len(result["nodes"]) == 1
        assert result["edges"] == []

    def test_node_contains_required_fields(self):
        """Each node has id, label, churn, and directory."""
        files = [
            FileForensics(
                path="src/auth.py",
                commits=10,
                lines_changed=200,
                complexity=200.0,
                authors=["alice@example.com"],
                coupled_with=[],
            )
        ]

        result = build_coupling_graph_data(files)
        node = result["nodes"][0]["data"]

        assert node["id"] == "src/auth.py"
        assert node["label"] == "auth.py"
        assert node["churn"] == 2000.0  # 10 commits * 200.0 complexity
        assert node["directory"] == "src"

    def test_edge_contains_required_fields(self):
        """Each edge has source, target, coupling, and crossModule."""
        files = [
            FileForensics(
                path="src/auth.py",
                commits=10,
                lines_changed=200,
                authors=["alice@example.com"],
                coupled_with=[CouplingInfo(file="src/user.py", ratio=0.65)],
            )
        ]

        result = build_coupling_graph_data(files)
        edge = result["edges"][0]["data"]

        assert edge["source"] == "src/auth.py"
        assert edge["target"] == "src/user.py"
        assert edge["coupling"] == 0.65
        assert "crossModule" in edge

    def test_coupling_creates_edge(self):
        """File with coupled_with list creates corresponding edges."""
        files = [
            FileForensics(
                path="src/auth.py",
                commits=10,
                lines_changed=200,
                authors=["alice@example.com"],
                coupled_with=[
                    CouplingInfo(file="src/user.py", ratio=0.8),
                    CouplingInfo(file="src/token.py", ratio=0.5),
                ],
            )
        ]

        result = build_coupling_graph_data(files)

        assert len(result["edges"]) == 2

    def test_cross_module_flag_true_for_different_directories(self):
        """Edge between files in different directories has crossModule=true."""
        files = [
            FileForensics(
                path="src/auth.py",
                commits=10,
                lines_changed=200,
                authors=["alice@example.com"],
                coupled_with=[CouplingInfo(file="tests/test_auth.py", ratio=0.9)],
            )
        ]

        result = build_coupling_graph_data(files)
        edge = result["edges"][0]["data"]

        assert edge["crossModule"] is True

    def test_cross_module_flag_false_for_same_directory(self):
        """Edge between files in same directory has crossModule=false."""
        files = [
            FileForensics(
                path="src/auth.py",
                commits=10,
                lines_changed=200,
                authors=["alice@example.com"],
                coupled_with=[CouplingInfo(file="src/user.py", ratio=0.8)],
            )
        ]

        result = build_coupling_graph_data(files)
        edge = result["edges"][0]["data"]

        assert edge["crossModule"] is False

    def test_edges_deduplicated(self):
        """A-B and B-A coupling creates only one edge."""
        files = [
            FileForensics(
                path="src/auth.py",
                commits=10,
                lines_changed=200,
                authors=["alice@example.com"],
                coupled_with=[CouplingInfo(file="src/user.py", ratio=0.8)],
            ),
            FileForensics(
                path="src/user.py",
                commits=5,
                lines_changed=100,
                authors=["bob@example.com"],
                coupled_with=[CouplingInfo(file="src/auth.py", ratio=0.8)],
            ),
        ]

        result = build_coupling_graph_data(files)

        # Should have 2 nodes but only 1 edge (deduplicated)
        assert len(result["nodes"]) == 2
        assert len(result["edges"]) == 1

    def test_max_churn_calculated(self):
        """Returns maxChurn for JavaScript size scaling."""
        files = [
            FileForensics(
                path="src/auth.py",
                commits=10,
                lines_changed=200,
                complexity=200.0,
                authors=["alice@example.com"],
                coupled_with=[],
            ),
            FileForensics(
                path="src/user.py",
                commits=5,
                lines_changed=50,
                complexity=50.0,
                authors=["bob@example.com"],
                coupled_with=[],
            ),
        ]

        result = build_coupling_graph_data(files)

        assert result["maxChurn"] == 2000.0  # max(10*200.0, 5*50.0)

    def test_root_level_file_directory(self):
        """Root-level files get directory='root'."""
        files = [
            FileForensics(
                path="README.md",
                commits=3,
                lines_changed=50,
                authors=["alice@example.com"],
                coupled_with=[],
            )
        ]

        result = build_coupling_graph_data(files)
        node = result["nodes"][0]["data"]

        assert node["directory"] == "root"

    def test_directories_list_populated(self):
        """Returns list of unique directories for color legend."""
        files = [
            FileForensics(
                path="src/auth.py",
                commits=10,
                lines_changed=200,
                authors=["alice@example.com"],
                coupled_with=[],
            ),
            FileForensics(
                path="tests/test_auth.py",
                commits=5,
                lines_changed=100,
                authors=["bob@example.com"],
                coupled_with=[],
            ),
        ]

        result = build_coupling_graph_data(files)

        assert "src" in result["directories"]
        assert "tests" in result["directories"]

    def test_coupled_target_not_in_files_creates_node(self):
        """Coupled target file not in files list still gets a node."""
        files = [
            FileForensics(
                path="src/auth.py",
                commits=10,
                lines_changed=200,
                authors=["alice@example.com"],
                coupled_with=[CouplingInfo(file="src/user.py", ratio=0.8)],
            )
        ]

        result = build_coupling_graph_data(files)

        # Should have 2 nodes: auth.py and user.py (created from coupling)
        node_ids = [n["data"]["id"] for n in result["nodes"]]
        assert "src/auth.py" in node_ids
        assert "src/user.py" in node_ids

    def test_edges_sorted_by_coupling_descending(self):
        """Edges are sorted by coupling ratio, highest first."""
        files = [
            FileForensics(
                path="src/auth.py",
                commits=10,
                lines_changed=200,
                authors=["alice@example.com"],
                coupled_with=[
                    CouplingInfo(file="src/low.py", ratio=0.35),
                    CouplingInfo(file="src/high.py", ratio=0.90),
                    CouplingInfo(file="src/mid.py", ratio=0.55),
                ],
            )
        ]

        result = build_coupling_graph_data(files)

        couplings = [e["data"]["coupling"] for e in result["edges"]]
        assert couplings == [0.90, 0.55, 0.35]

    def test_total_edges_field_present(self):
        """Result includes totalEdges count for slider max."""
        files = [
            FileForensics(
                path="src/auth.py",
                commits=10,
                lines_changed=200,
                authors=["alice@example.com"],
                coupled_with=[
                    CouplingInfo(file="src/a.py", ratio=0.5),
                    CouplingInfo(file="src/b.py", ratio=0.6),
                    CouplingInfo(file="src/c.py", ratio=0.7),
                ],
            )
        ]

        result = build_coupling_graph_data(files)

        assert result["totalEdges"] == 3
