"""HTML report generator for forensic analysis."""

from black_box_unlock.core.models import AnalysisResult

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Code Forensics: {repo}</title>
    <style>
        :root {{
            --bg: #1a1a2e;
            --surface: #16213e;
            --primary: #e94560;
            --secondary: #0f3460;
            --text: #eaeaea;
            --muted: #a0a0a0;
            --warning: #f39c12;
            --success: #27ae60;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
            padding: 2rem;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{
            font-size: 2rem;
            margin-bottom: 0.5rem;
            color: var(--primary);
        }}
        .subtitle {{
            color: var(--muted);
            margin-bottom: 2rem;
        }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .stat-card {{
            background: var(--surface);
            padding: 1.5rem;
            border-radius: 8px;
            border-left: 4px solid var(--primary);
        }}
        .stat-value {{
            font-size: 2rem;
            font-weight: bold;
            color: var(--primary);
        }}
        .stat-label {{
            color: var(--muted);
            font-size: 0.875rem;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--surface);
            border-radius: 8px;
            overflow: hidden;
        }}
        th, td {{
            padding: 1rem;
            text-align: left;
            border-bottom: 1px solid var(--secondary);
        }}
        th {{
            background: var(--secondary);
            font-weight: 600;
            color: var(--text);
        }}
        tr:hover {{ background: rgba(233, 69, 96, 0.1); }}
        .high-risk {{
            color: var(--warning);
            font-weight: 600;
        }}
        .coupling {{
            font-size: 0.875rem;
            color: var(--muted);
        }}
        .coupling-item {{
            display: inline-block;
            background: var(--secondary);
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            margin: 0.125rem;
            font-size: 0.75rem;
        }}
        .hotspot {{
            background: linear-gradient(90deg, var(--primary), transparent);
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
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
</body>
</html>
"""

FILE_ROW_TEMPLATE = """                <tr>
                    <td>{path}</td>
                    <td><span class="hotspot">{hotspot_score}</span></td>
                    <td>{commits}</td>
                    <td>{lines_changed}</td>
                    <td class="{risk_class}">{author_count}</td>
                    <td class="coupling">{coupling_html}</td>
                </tr>"""


def generate_html_report(result: AnalysisResult) -> str:
    """Generate HTML report from analysis result.

    Args:
        result: The analysis result to render.

    Returns:
        Complete HTML document as string.
    """
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
                commits=file.commits,
                lines_changed=file.lines_changed,
                author_count=file.author_count,
                risk_class=risk_class,
                coupling_html=coupling_html,
            )
        )

    return HTML_TEMPLATE.format(
        repo=result.repo,
        days=result.analyzed_days,
        generated_at=result.generated_at.strftime("%Y-%m-%d %H:%M"),
        total_files=result.summary.total_files,
        high_risk=result.summary.high_risk_ownership,
        coupled_pairs=result.summary.coupled_pairs,
        file_rows="\n".join(file_rows),
    )
