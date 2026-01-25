"""Black Box Unlock CLI - Code forensics commands."""

from enum import Enum
from pathlib import Path

import typer
from rich.console import Console

from black_box_unlock.analysis import export_to_json, run_analysis
from black_box_unlock.visualization.html import generate_html_report

app = typer.Typer(
    name="bbu",
    help="Black Box Unlock - Code forensics tool. Investigate your codebase like a crime scene.",
    no_args_is_help=True,
)
console = Console()


class OutputFormat(str, Enum):
    json = "json"
    html = "html"


@app.command()
def analyze_repo(
    days: int = typer.Option(30, help="Days of git history to analyze"),
    output: OutputFormat = typer.Option(OutputFormat.json, help="Output format: json, html"),
    min_coupling: float = typer.Option(0.3, help="Minimum coupling ratio to include"),
) -> None:
    """Analyze repository git history for code forensics.

    Extracts file churn, temporal coupling, and ownership patterns
    from git history. Based on 'Your Code as a Crime Scene' methodology.
    """
    repo_path = Path(".")
    result = run_analysis(repo_path, days=days, min_coupling=min_coupling)

    match output:
        case OutputFormat.json:
            console.print(export_to_json(result))
        case OutputFormat.html:
            console.print(generate_html_report(result))


@app.command()
def version() -> None:
    """Show version information."""
    from black_box_unlock import __version__

    console.print(f"Black Box Unlock v{__version__}")


if __name__ == "__main__":
    app()
