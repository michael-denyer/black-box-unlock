"""Black Box Unlock CLI - Code forensics commands."""

from enum import Enum
from pathlib import Path

import typer
from rich.console import Console

from black_box_unlock.analysis import export_to_json, run_analysis
from black_box_unlock.core.logging import configure_logging
from black_box_unlock.visualization.html import generate_html_report


def _version_callback(value: bool) -> None:
    if value:
        from black_box_unlock import __version__

        print(f"Black Box Unlock v{__version__}")
        raise typer.Exit()


def _main_callback(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
    version: bool | None = typer.Option(
        None, "--version", callback=_version_callback, is_eager=True
    ),
) -> None:
    """Configure logging based on verbose flag."""
    configure_logging(verbose=verbose)


# [1a] CLI App - Typer application with `bbu` command
app = typer.Typer(
    name="bbu",
    help="Black Box Unlock - Code forensics tool. Investigate your codebase like a crime scene.",
    no_args_is_help=True,
    callback=_main_callback,
)
console = Console()


class OutputFormat(str, Enum):
    json = "json"
    html = "html"


@app.command()
def analyze_repo(  # [1a.1] Main analysis command
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
            # Use print() instead of console.print() to avoid Rich markup interpretation
            # Rich would strip [dir], [data-tab=...] etc. as invalid markup tags
            print(generate_html_report(result))


@app.command()
def version() -> None:  # [1a.2] Version info command
    """Show version information."""
    _version_callback(True)


if __name__ == "__main__":
    app()
