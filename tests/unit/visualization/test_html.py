"""Unit tests for HTML report generator."""

from datetime import datetime

from black_box_unlock.core.models import (
    AnalysisResult,
    AnalysisSummary,
    CouplingInfo,
    FileForensics,
)
from black_box_unlock.visualization.html import generate_html_report


class TestGenerateHtmlReport:
    """Tests for generate_html_report function."""

    def test_generates_valid_html(self):
        """Generates complete HTML document."""
        result = AnalysisResult(
            repo="test-repo",
            analyzed_days=30,
            generated_at=datetime(2026, 1, 25, 15, 30, 0),
            files=[
                FileForensics(
                    path="src/auth.py",
                    commits=10,
                    lines_changed=200,
                    authors=["alice@example.com"],
                    coupled_with=[],
                )
            ],
            summary=AnalysisSummary(
                total_files=1,
                high_risk_ownership=0,
                coupled_pairs=0,
            ),
        )

        html = generate_html_report(result)

        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html
        assert "test-repo" in html

    def test_includes_summary_stats(self):
        """Includes summary statistics in report."""
        result = AnalysisResult(
            repo="test-repo",
            analyzed_days=30,
            generated_at=datetime(2026, 1, 25, 15, 30, 0),
            files=[],
            summary=AnalysisSummary(
                total_files=42,
                high_risk_ownership=5,
                coupled_pairs=8,
            ),
        )

        html = generate_html_report(result)

        assert "42" in html  # total files
        assert "5" in html  # high risk
        assert "8" in html  # coupled pairs

    def test_includes_file_table(self):
        """Includes table with file data."""
        result = AnalysisResult(
            repo="test-repo",
            analyzed_days=30,
            generated_at=datetime(2026, 1, 25, 15, 30, 0),
            files=[
                FileForensics(
                    path="src/auth.py",
                    commits=10,
                    lines_changed=200,
                    authors=["alice@example.com", "bob@example.com"],
                    coupled_with=[CouplingInfo(file="src/user.py", ratio=0.8)],
                )
            ],
            summary=AnalysisSummary(
                total_files=1,
                high_risk_ownership=0,
                coupled_pairs=1,
            ),
        )

        html = generate_html_report(result)

        assert "src/auth.py" in html
        assert "<table" in html
        assert "2000" in html  # hotspot score (10 * 200)

    def test_highlights_high_risk_files(self):
        """High risk files are highlighted."""
        result = AnalysisResult(
            repo="test-repo",
            analyzed_days=30,
            generated_at=datetime(2026, 1, 25, 15, 30, 0),
            files=[
                FileForensics(
                    path="src/risky.py",
                    commits=10,
                    lines_changed=200,
                    authors=["a@x.com", "b@x.com", "c@x.com", "d@x.com"],
                    coupled_with=[],
                )
            ],
            summary=AnalysisSummary(
                total_files=1,
                high_risk_ownership=1,
                coupled_pairs=0,
            ),
        )

        html = generate_html_report(result)

        # Should have some indicator for high risk
        assert "high-risk" in html or "warning" in html or "risk" in html.lower()

    def test_includes_coupling_info(self):
        """Coupling information is shown for files."""
        result = AnalysisResult(
            repo="test-repo",
            analyzed_days=30,
            generated_at=datetime(2026, 1, 25, 15, 30, 0),
            files=[
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
            ],
            summary=AnalysisSummary(
                total_files=1,
                high_risk_ownership=0,
                coupled_pairs=2,
            ),
        )

        html = generate_html_report(result)

        assert "src/user.py" in html
        assert "src/token.py" in html

    def test_includes_plotly_cdn(self):
        """HTML includes Plotly.js CDN script."""
        result = AnalysisResult(
            repo="test-repo",
            analyzed_days=30,
            generated_at=datetime(2026, 1, 25, 15, 30, 0),
            files=[],
            summary=AnalysisSummary(
                total_files=0,
                high_risk_ownership=0,
                coupled_pairs=0,
            ),
        )

        html = generate_html_report(result)

        assert "plotly" in html.lower()
        assert "<script" in html

    def test_includes_tab_navigation(self):
        """HTML includes tab navigation for Hotspots, Table, Coupling."""
        result = AnalysisResult(
            repo="test-repo",
            analyzed_days=30,
            generated_at=datetime(2026, 1, 25, 15, 30, 0),
            files=[],
            summary=AnalysisSummary(
                total_files=0,
                high_risk_ownership=0,
                coupled_pairs=0,
            ),
        )

        html = generate_html_report(result)

        assert "Hotspots" in html
        assert "Table" in html
        assert "Coupling" in html

    def test_includes_treemap_container(self):
        """HTML includes container for Plotly treemap."""
        result = AnalysisResult(
            repo="test-repo",
            analyzed_days=30,
            generated_at=datetime(2026, 1, 25, 15, 30, 0),
            files=[],
            summary=AnalysisSummary(
                total_files=0,
                high_risk_ownership=0,
                coupled_pairs=0,
            ),
        )

        html = generate_html_report(result)

        assert 'id="treemap"' in html or "treemap" in html.lower()

    def test_embeds_treemap_data_as_json(self):
        """Treemap data is embedded as JSON in the HTML."""
        result = AnalysisResult(
            repo="test-repo",
            analyzed_days=30,
            generated_at=datetime(2026, 1, 25, 15, 30, 0),
            files=[
                FileForensics(
                    path="src/auth.py",
                    commits=10,
                    lines_changed=200,
                    authors=["alice@example.com"],
                    coupled_with=[],
                )
            ],
            summary=AnalysisSummary(
                total_files=1,
                high_risk_ownership=0,
                coupled_pairs=0,
            ),
        )

        html = generate_html_report(result)

        # Treemap data should be embedded as JSON
        assert '"labels"' in html
        assert '"parents"' in html
        assert '"values"' in html
        assert '"hovertext"' in html

    def test_includes_cytoscape_cdn(self):
        """HTML includes Cytoscape.js CDN script."""
        result = AnalysisResult(
            repo="test-repo",
            analyzed_days=30,
            generated_at=datetime(2026, 1, 25, 15, 30, 0),
            files=[],
            summary=AnalysisSummary(
                total_files=0,
                high_risk_ownership=0,
                coupled_pairs=0,
            ),
        )

        html = generate_html_report(result)

        assert "cytoscape" in html.lower()

    def test_includes_coupling_graph_container(self):
        """HTML includes container for Cytoscape coupling graph."""
        result = AnalysisResult(
            repo="test-repo",
            analyzed_days=30,
            generated_at=datetime(2026, 1, 25, 15, 30, 0),
            files=[],
            summary=AnalysisSummary(
                total_files=0,
                high_risk_ownership=0,
                coupled_pairs=0,
            ),
        )

        html = generate_html_report(result)

        assert 'id="coupling-graph"' in html

    def test_embeds_coupling_data_as_json(self):
        """Coupling graph data is embedded as JSON in the HTML."""
        result = AnalysisResult(
            repo="test-repo",
            analyzed_days=30,
            generated_at=datetime(2026, 1, 25, 15, 30, 0),
            files=[
                FileForensics(
                    path="src/auth.py",
                    commits=10,
                    lines_changed=200,
                    authors=["alice@example.com"],
                    coupled_with=[CouplingInfo(file="src/user.py", ratio=0.8)],
                )
            ],
            summary=AnalysisSummary(
                total_files=1,
                high_risk_ownership=0,
                coupled_pairs=1,
            ),
        )

        html = generate_html_report(result)

        # Coupling graph data should be embedded as JSON
        assert '"nodes"' in html
        assert '"edges"' in html
        assert '"directories"' in html
        assert '"maxChurn"' in html

    def test_coupling_slider_present(self):
        """Coupling tab has slider control for top N edges."""
        result = AnalysisResult(
            repo="test-repo",
            analyzed_days=30,
            generated_at=datetime(2026, 1, 25, 15, 30, 0),
            files=[],
            summary=AnalysisSummary(
                total_files=0,
                high_risk_ownership=0,
                coupled_pairs=0,
            ),
        )

        html = generate_html_report(result)

        assert 'id="edge-slider"' in html
        assert 'id="edge-count"' in html

    def test_filter_top_n_function_present(self):
        """JavaScript includes filterTopN function."""
        result = AnalysisResult(
            repo="test-repo",
            analyzed_days=30,
            generated_at=datetime(2026, 1, 25, 15, 30, 0),
            files=[],
            summary=AnalysisSummary(
                total_files=0,
                high_risk_ownership=0,
                coupled_pairs=0,
            ),
        )

        html = generate_html_report(result)

        assert "function filterTopN(" in html

    def test_focus_functions_present(self):
        """JavaScript includes focusNode and clearFocus functions."""
        result = AnalysisResult(
            repo="test-repo",
            analyzed_days=30,
            generated_at=datetime(2026, 1, 25, 15, 30, 0),
            files=[],
            summary=AnalysisSummary(
                total_files=0,
                high_risk_ownership=0,
                coupled_pairs=0,
            ),
        )

        html = generate_html_report(result)

        assert "function focusNode(" in html
        assert "function clearFocus(" in html

    def test_tooltip_element_present(self):
        """Coupling tab has tooltip element."""
        result = AnalysisResult(
            repo="test-repo",
            analyzed_days=30,
            generated_at=datetime(2026, 1, 25, 15, 30, 0),
            files=[],
            summary=AnalysisSummary(
                total_files=0,
                high_risk_ownership=0,
                coupled_pairs=0,
            ),
        )

        html = generate_html_report(result)

        assert 'id="coupling-tooltip"' in html
