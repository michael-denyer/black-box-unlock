"""Black Box Unlock CLI - Code forensics commands."""

import json
from enum import Enum
from pathlib import Path

import typer
from rich.console import Console

from black_box_unlock.analysis import export_to_json, run_analysis
from black_box_unlock.core.exceptions import BlackBoxUnlockError
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
    no_ci: bool = typer.Option(False, "--no-ci", help="Skip CI failure analysis"),
    repo: Path = typer.Option(Path("."), "--repo", help="Path to the git repository to analyze"),
) -> None:
    """Analyze repository git history for code forensics.

    Extracts file churn, temporal coupling, and ownership patterns
    from git history. Based on 'Your Code as a Crime Scene' methodology.
    """
    repo_path = repo
    try:
        result = run_analysis(repo_path, days=days, min_coupling=min_coupling, include_ci=not no_ci)
    except BlackBoxUnlockError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e

    match output:
        case OutputFormat.json:
            console.print(export_to_json(result))
        case OutputFormat.html:
            # Use print() instead of console.print() to avoid Rich markup interpretation
            # Rich would strip [dir], [data-tab=...] etc. as invalid markup tags
            print(generate_html_report(result))


@app.command()
def coupling_guard(
    file: str = typer.Argument(..., help="Repo-relative path of the edited file"),
    repo: Path = typer.Option(Path("."), "--repo", help="Repository root"),
    threshold: float = typer.Option(0.5, "--threshold", help="Minimum coupling ratio to warn"),
) -> None:
    """Emit a Claude Code hook warning when the edited file has strong temporal coupling.

    Designed for PostToolUse hooks: prints hook JSON when there is something
    to say, nothing otherwise. Never fails - a guard must not break an edit.
    """
    from black_box_unlock.guard import coupling_warnings

    try:
        warnings = coupling_warnings(file, repo, threshold)
    except Exception:
        # A guard must never break the edit it observes; degrade to silence.
        raise typer.Exit(code=0) from None
    if warnings:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": " ".join(warnings),
                    }
                }
            )
        )


@app.command()
def version() -> None:  # [1a.2] Version info command
    """Show version information."""
    _version_callback(True)


if __name__ == "__main__":
    app()
