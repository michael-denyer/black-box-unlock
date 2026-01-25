"""HTML report generator for forensic analysis."""

import json

from black_box_unlock.core.models import AnalysisResult
from black_box_unlock.visualization.treemap import build_treemap_data

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Code Forensics: {repo}</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        :root {{
            --bg: #f5f5f5;
            --surface: #ffffff;
            --primary: #5a5a5a;
            --secondary: #e0e0e0;
            --accent: #4a7c59;
            --text: #333333;
            --muted: #777777;
            --warning: #c0392b;
            --success: #4a7c59;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: Inter, -apple-system, BlinkMacSystemFont, Helvetica Neue, Arial, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
            padding: 2rem;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        h1 {{
            font-size: 1.75rem;
            margin-bottom: 0.5rem;
            color: var(--text);
            font-weight: 500;
        }}
        .subtitle {{
            color: var(--muted);
            margin-bottom: 2rem;
            font-size: 0.9rem;
        }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .stat-card {{
            background: var(--surface);
            padding: 1.25rem;
            border-radius: 6px;
            border: 1px solid var(--secondary);
            border-left: 3px solid var(--accent);
        }}
        .stat-card:nth-child(2) {{ border-left-color: #e09850; }}
        .stat-card:nth-child(3) {{ border-left-color: #6b8cae; }}
        .stat-value {{
            font-size: 1.75rem;
            font-weight: 600;
            color: var(--text);
        }}
        .stat-label {{
            color: var(--muted);
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .tabs {{
            display: flex;
            gap: 0;
            margin-bottom: 0;
            border-bottom: 1px solid var(--secondary);
        }}
        .tab {{
            padding: 0.75rem 1.5rem;
            background: transparent;
            border: none;
            border-bottom: 2px solid transparent;
            color: var(--muted);
            cursor: pointer;
            font-size: 0.9rem;
            font-weight: 500;
            transition: all 0.2s;
        }}
        .tab:hover {{
            color: var(--text);
        }}
        .tab.active {{
            color: var(--text);
            border-bottom-color: var(--accent);
        }}
        .tab-content {{
            display: none;
            padding-top: 1.5rem;
        }}
        .tab-content.active {{
            display: block;
        }}
        #treemap {{
            width: 100%;
            min-height: 600px;
            height: calc(100vh - 350px);
            background: var(--surface);
            border-radius: 6px;
            border: 1px solid var(--secondary);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--surface);
            border-radius: 6px;
            overflow: hidden;
            border: 1px solid var(--secondary);
        }}
        th, td {{
            padding: 0.875rem 1rem;
            text-align: left;
            border-bottom: 1px solid var(--secondary);
        }}
        th {{
            background: var(--primary);
            font-weight: 500;
            color: white;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        tr:hover {{ background: #fafafa; }}
        .high-risk {{
            color: var(--warning);
            font-weight: 600;
        }}
        .coupling {{
            font-size: 0.8rem;
            color: var(--muted);
        }}
        .coupling-item {{
            display: inline-block;
            background: var(--secondary);
            padding: 0.2rem 0.5rem;
            border-radius: 3px;
            margin: 0.1rem;
            font-size: 0.75rem;
        }}
        .hotspot {{
            display: inline-block;
            padding: 0.25rem 0.6rem;
            border-radius: 4px;
            font-weight: 600;
            font-size: 0.85rem;
            color: white;
        }}
        .hotspot-low {{ background: #5a9a68; }}
        .hotspot-med {{ background: #d4c34a; color: #333; }}
        .hotspot-high {{ background: #e09850; }}
        .hotspot-critical {{ background: #cb4b3f; }}
        .metric {{
            display: inline-block;
            padding: 0.15rem 0.4rem;
            border-radius: 3px;
            font-size: 0.85rem;
        }}
        .metric-high {{ background: rgba(203, 75, 63, 0.15); color: #a33; font-weight: 500; }}
        .metric-med {{ background: rgba(224, 152, 80, 0.15); color: #965; }}
        .placeholder {{
            padding: 3rem;
            text-align: center;
            color: var(--muted);
            background: var(--surface);
            border-radius: 6px;
            border: 1px solid var(--secondary);
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Code Forensics Report</h1>
        <p class="subtitle">{repo} &bull; {days} days analyzed &bull; Generated {generated_at}</p>

        <div class="summary">
            <div class="stat-card">
                <div class="stat-value">{total_files}</div>
                <div class="stat-label">Total Files</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{high_risk}</div>
                <div class="stat-label">High Risk Ownership</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{coupled_pairs}</div>
                <div class="stat-label">Coupled Pairs</div>
            </div>
        </div>

        <div class="tabs">
            <button class="tab active" data-tab="table">Table</button>
            <button class="tab" data-tab="hotspots">Hotspots</button>
            <button class="tab" data-tab="coupling">Coupling</button>
        </div>

        <div id="table" class="tab-content active">
            <table>
                <thead>
                    <tr>
                        <th>File</th>
                        <th>Hotspot Score</th>
                        <th>Commits</th>
                        <th>Lines Changed</th>
                        <th>Authors</th>
                        <th>Coupled With</th>
                    </tr>
                </thead>
                <tbody>
{file_rows}
                </tbody>
            </table>
        </div>

        <div id="hotspots" class="tab-content">
            <div id="treemap"></div>
        </div>

        <div id="coupling" class="tab-content">
            <div class="placeholder">
                Temporal coupling graph coming soon
            </div>
        </div>
    </div>

    <script>
        // Tab switching
        document.querySelectorAll('.tab').forEach(tab => {{
            tab.addEventListener('click', () => {{
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                tab.classList.add('active');
                document.getElementById(tab.dataset.tab).classList.add('active');
            }});
        }});

        // Treemap data
        const treemapData = {treemap_json};

        // Render treemap with green-yellow-red colorscale
        Plotly.newPlot('treemap', [{{
            type: 'treemap',
            labels: treemapData.labels,
            parents: treemapData.parents,
            values: treemapData.values,
            marker: {{
                colors: treemapData.colors,
                colorscale: [
                    [0, '#5a9a68'],
                    [0.3, '#a8c256'],
                    [0.5, '#d4c34a'],
                    [0.7, '#e09850'],
                    [1, '#cb4b3f']
                ],
                showscale: true,
                colorbar: {{
                    title: 'Hotspot',
                    tickfont: {{ color: '#444' }},
                    titlefont: {{ color: '#444' }},
                    len: 0.5,
                    thickness: 15,
                    x: 1.02,
                    xpad: 5
                }}
            }},
            customdata: treemapData.customdata,
            hovertemplate: '<b>%{{label}}</b><br>Lines: %{{value}}<br>Hotspot: %{{color:,.0f}}<extra></extra>',
            textinfo: 'label+value',
            insidetextfont: {{ color: '#fff' }},
            outsidetextfont: {{ color: '#444' }},
            pathbar: {{ visible: true, edgeshape: '>' }}
        }}], {{
            margin: {{ t: 30, l: 0, r: 80, b: 0 }},
            paper_bgcolor: '#ffffff',
            plot_bgcolor: '#ffffff',
            font: {{ color: '#444', family: 'Inter, Roboto, Helvetica Neue, Arial, sans-serif' }},
            autosize: true
        }}, {{
            responsive: true
        }});

        // Force resize to fill container
        window.addEventListener('resize', () => Plotly.Plots.resize('treemap'));
        setTimeout(() => Plotly.Plots.resize('treemap'), 100);
    </script>
</body>
</html>
"""

FILE_ROW_TEMPLATE = """                <tr>
                    <td>{path}</td>
                    <td><span class="hotspot {hotspot_class}">{hotspot_score:,}</span></td>
                    <td><span class="metric {commits_class}">{commits}</span></td>
                    <td><span class="metric {lines_class}">{lines_changed:,}</span></td>
                    <td class="{risk_class}">{author_count}</td>
                    <td class="coupling">{coupling_html}</td>
                </tr>"""


def _get_severity_class(value: int, max_val: int, prefix: str) -> str:
    """Return CSS class based on value relative to max."""
    if max_val == 0:
        return ""
    ratio = value / max_val
    if ratio >= 0.75:
        return f"{prefix}-critical" if prefix == "hotspot" else f"{prefix}-high"
    if ratio >= 0.5:
        return f"{prefix}-high" if prefix == "hotspot" else f"{prefix}-med"
    if ratio >= 0.25:
        return f"{prefix}-med" if prefix == "hotspot" else ""
    return f"{prefix}-low" if prefix == "hotspot" else ""


def generate_html_report(result: AnalysisResult) -> str:
    """Generate HTML report from analysis result.

    Args:
        result: The analysis result to render.

    Returns:
        Complete HTML document as string.
    """
    # Calculate max values for severity thresholds
    max_hotspot = max((f.hotspot_score for f in result.files), default=0)
    max_commits = max((f.commits for f in result.files), default=0)
    max_lines = max((f.lines_changed for f in result.files), default=0)

    file_rows = []
    for file in result.files:
        coupling_html = ""
        if file.coupled_with:
            coupling_items = [
                f'<span class="coupling-item">{c.file} ({c.ratio:.0%})</span>'
                for c in file.coupled_with
            ]
            coupling_html = " ".join(coupling_items)

        risk_class = "high-risk" if file.is_high_risk else ""

        file_rows.append(
            FILE_ROW_TEMPLATE.format(
                path=file.path,
                hotspot_score=file.hotspot_score,
                hotspot_class=_get_severity_class(file.hotspot_score, max_hotspot, "hotspot"),
                commits=file.commits,
                commits_class=_get_severity_class(file.commits, max_commits, "metric"),
                lines_changed=file.lines_changed,
                lines_class=_get_severity_class(file.lines_changed, max_lines, "metric"),
                author_count=file.author_count,
                risk_class=risk_class,
                coupling_html=coupling_html,
            )
        )

    # Build treemap data
    treemap_data = build_treemap_data(result.files)

    return HTML_TEMPLATE.format(
        repo=result.repo,
        days=result.analyzed_days,
        generated_at=result.generated_at.strftime("%Y-%m-%d %H:%M"),
        total_files=result.summary.total_files,
        high_risk=result.summary.high_risk_ownership,
        coupled_pairs=result.summary.coupled_pairs,
        file_rows="\n".join(file_rows),
        treemap_json=json.dumps(treemap_data),
    )
