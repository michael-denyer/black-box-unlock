"""Black Box Unlock CLI - Code forensics commands."""

import typer
from rich.console import Console

app = typer.Typer(
    name="bbu",
    help="Black Box Unlock - Code forensics tool. Investigate your codebase like a crime scene.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def analyze_repo(
    days: int = typer.Option(30, help="Days of git history to analyze"),
    hotspots: bool = typer.Option(False, "--hotspots", help="Show file hotspots"),
    output: str = typer.Option("text", help="Output format: text, json, markdown"),
) -> None:
    """Analyze repository git history for code forensics.

    Extracts file churn, temporal coupling, and ownership patterns
    from git history. Based on 'Your Code as a Crime Scene' methodology.
    """
    console.print(f"[bold]Analyzing repository (last {days} days)...[/bold]")
    console.print("[yellow]Not yet implemented - see BBU-t40 epic[/yellow]")


@app.command()
def version() -> None:
    """Show version information."""
    from black_box_unlock import __version__

    console.print(f"Black Box Unlock v{__version__}")


if __name__ == "__main__":
    app()
