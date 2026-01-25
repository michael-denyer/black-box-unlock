"""Unit tests for treemap data transformation."""

from black_box_unlock.core.models import CouplingInfo, FileForensics
from black_box_unlock.visualization.treemap import build_treemap_data


class TestBuildTreemapData:
    """Tests for build_treemap_data function."""

    def test_empty_files_returns_root_only(self):
        """Empty file list returns minimal structure with just root."""
        result = build_treemap_data([])

        assert result["labels"] == [""]
        assert result["parents"] == [""]
        assert result["values"] == [0]

    def test_single_file_creates_hierarchy(self):
        """Single file creates path hierarchy."""
        files = [
            FileForensics(
                path="src/auth.py",
                commits=10,
                lines_changed=200,
                authors=["alice@example.com"],
                coupled_with=[],
            )
        ]

        result = build_treemap_data(files)

        # Should have: root, src, auth.py
        assert "" in result["labels"]  # root
        assert "src" in result["labels"]
        assert "auth.py" in result["labels"]

        # auth.py's parent should be src
        auth_idx = result["labels"].index("auth.py")
        assert result["parents"][auth_idx] == "src"

        # src's parent should be root
        src_idx = result["labels"].index("src")
        assert result["parents"][src_idx] == ""

    def test_file_values_are_lines_changed(self):
        """Leaf files have values set to lines_changed."""
        files = [
            FileForensics(
                path="src/auth.py",
                commits=10,
                lines_changed=200,
                authors=["alice@example.com"],
                coupled_with=[],
            )
        ]

        result = build_treemap_data(files)

        auth_idx = result["labels"].index("auth.py")
        assert result["values"][auth_idx] == 200

    def test_directory_values_are_zero(self):
        """Directory nodes have value=0 (Plotly sums children)."""
        files = [
            FileForensics(
                path="src/auth.py",
                commits=10,
                lines_changed=200,
                authors=["alice@example.com"],
                coupled_with=[],
            )
        ]

        result = build_treemap_data(files)

        src_idx = result["labels"].index("src")
        assert result["values"][src_idx] == 0

    def test_directory_customdata_is_minimal(self):
        """Directory nodes have minimal customdata for hover."""
        files = [
            FileForensics(
                path="src/auth.py",
                commits=10,
                lines_changed=200,
                authors=["alice@example.com"],
                coupled_with=[],
            )
        ]

        result = build_treemap_data(files)

        src_idx = result["labels"].index("src")
        customdata = result["customdata"][src_idx]
        assert customdata["is_dir"] is True
        assert customdata["path"] == "src"
        assert customdata["hover"] == "src"

    def test_colors_are_hotspot_scores(self):
        """Colors array contains hotspot scores for files."""
        files = [
            FileForensics(
                path="src/auth.py",
                commits=10,
                lines_changed=200,
                authors=["alice@example.com"],
                coupled_with=[],
            )
        ]

        result = build_treemap_data(files)

        auth_idx = result["labels"].index("auth.py")
        assert result["colors"][auth_idx] == 2000  # 10 * 200

    def test_multiple_files_same_directory(self):
        """Multiple files in same directory share parent."""
        files = [
            FileForensics(
                path="src/auth.py",
                commits=10,
                lines_changed=100,
                authors=["alice@example.com"],
                coupled_with=[],
            ),
            FileForensics(
                path="src/user.py",
                commits=5,
                lines_changed=50,
                authors=["bob@example.com"],
                coupled_with=[],
            ),
        ]

        result = build_treemap_data(files)

        auth_idx = result["labels"].index("auth.py")
        user_idx = result["labels"].index("user.py")

        # Both should have src as parent
        assert result["parents"][auth_idx] == "src"
        assert result["parents"][user_idx] == "src"

        # src should only appear once
        assert result["labels"].count("src") == 1

    def test_nested_directories(self):
        """Deeply nested paths create correct hierarchy."""
        files = [
            FileForensics(
                path="src/auth/handlers/login.py",
                commits=10,
                lines_changed=200,
                authors=["alice@example.com"],
                coupled_with=[],
            )
        ]

        result = build_treemap_data(files)

        # Check hierarchy: root -> src -> auth -> handlers -> login.py
        login_idx = result["labels"].index("login.py")
        assert result["parents"][login_idx] == "handlers"

        handlers_idx = result["labels"].index("handlers")
        assert result["parents"][handlers_idx] == "auth"

        auth_idx = result["labels"].index("auth")
        assert result["parents"][auth_idx] == "src"

    def test_customdata_includes_file_details(self):
        """Customdata contains file metadata for tooltips."""
        files = [
            FileForensics(
                path="src/auth.py",
                commits=10,
                lines_changed=200,
                authors=["alice@example.com", "bob@example.com"],
                coupled_with=[CouplingInfo(file="src/user.py", ratio=0.8)],
            )
        ]

        result = build_treemap_data(files)

        auth_idx = result["labels"].index("auth.py")
        customdata = result["customdata"][auth_idx]

        assert customdata["commits"] == 10
        assert customdata["author_count"] == 2
        assert customdata["is_high_risk"] is False
        assert len(customdata["coupled_with"]) == 1
        assert "hover" in customdata
        assert "src/auth.py" in customdata["hover"]
