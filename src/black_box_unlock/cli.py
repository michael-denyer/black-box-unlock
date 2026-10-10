"""Black Box Unlock CLI - Code forensics commands."""

import json
import shutil
import sys
from enum import Enum
from pathlib import Path

import typer
from loguru import logger
from rich.console import Console

from black_box_unlock.analysis import export_to_json, run_analysis
from black_box_unlock.config import load_project_config
from black_box_unlock.core.exceptions import BlackBoxUnlockError
from black_box_unlock.core.logging import configure_logging
from black_box_unlock.git.changes import BaseChange, StagedChange, WorkingTreeChange
from black_box_unlock.review import ChangeReviewRequest, run_change_review
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


def _review_selector(
    base: str | None,
    staged: bool,
    working_tree: bool,
) -> BaseChange | StagedChange | WorkingTreeChange:
    selected = sum((base is not None, staged, working_tree))
    if selected > 1:
        raise typer.BadParameter("--base, --staged, and --working-tree are mutually exclusive")
    if base is not None:
        return BaseChange(base_ref=base)
    if staged:
        return StagedChange()
    return WorkingTreeChange()


@app.command()
def analyze_repo(  # [1a.1] Main analysis command
    days: int = typer.Option(30, help="Days of git history to analyze"),
    output: OutputFormat = typer.Option(OutputFormat.json, help="Output format: json, html"),
    min_coupling: float = typer.Option(0.3, help="Minimum coupling ratio to include"),
    no_ci: bool = typer.Option(False, "--no-ci", help="Skip CI failure analysis"),
    repo: Path = typer.Option(Path("."), "--repo", help="Path to the git repository to analyze"),
    xray_top: int = typer.Option(
        5, "--xray-top", help="Auto X-Ray the top N hotspot files (0 disables)"
    ),
) -> None:
    """Analyze repository git history for code forensics.

    Extracts file churn, temporal coupling, and ownership patterns
    from git history. Based on 'Your Code as a Crime Scene' methodology.
    """
    repo_path = repo
    try:
        result = run_analysis(
            repo_path,
            days=days,
            min_coupling=min_coupling,
            include_ci=not no_ci,
            xray_top=xray_top,
        )
    except BlackBoxUnlockError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e

    match output:
        case OutputFormat.json:
            # print() not console.print(): Rich wraps at terminal width, which
            # inserts newlines inside JSON strings longer than ~80 chars
            print(export_to_json(result))
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
    except Exception as e:
        # A guard must never break the edit it observes; degrade to silence — but
        # log so a permanently-failing guard stays diagnosable instead of silently dead.
        logger.warning("coupling guard skipped for {}: {}", file, e)
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


@app.command("coupling-guard-hook", hidden=True)
def coupling_guard_hook(
    repo: Path = typer.Option(Path("."), "--repo", help="Repository root"),
) -> None:
    """Parse a Claude PostToolUse payload and emit a quiet coupling warning."""
    from black_box_unlock.guard import coupling_warnings

    try:
        payload = json.loads(sys.stdin.read())
        raw_path = payload.get("tool_input", {}).get("file_path")
        if not isinstance(raw_path, str) or not raw_path:
            return
        repo_root = repo.resolve()
        candidate = Path(raw_path)
        absolute_path = (
            candidate.resolve() if candidate.is_absolute() else (repo_root / candidate).resolve()
        )
        file_path = absolute_path.relative_to(repo_root).as_posix()
        warnings = coupling_warnings(file_path, repo_root)
    except Exception as error:
        logger.warning("coupling guard hook skipped: {}", error)
        return
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


@app.command("review-change")
def review_change_command(
    base: str | None = typer.Option(
        None,
        "--base",
        help="Review branch and local work from this ref's merge base",
    ),
    staged: bool = typer.Option(False, "--staged", help="Review only the index"),
    working_tree: bool = typer.Option(
        False,
        "--working-tree",
        help="Review unstaged and untracked files (the default)",
    ),
    repo: Path = typer.Option(Path("."), "--repo", help="Repository root"),
    profile: str | None = typer.Option(
        None,
        "--profile",
        help="Named review profile from .bbu.toml",
    ),
    days: int | None = typer.Option(
        None,
        "--days",
        help="Override the profile's history window",
    ),
    min_coupling: float | None = typer.Option(
        None,
        "--min-coupling",
        help="Override the profile's minimum observed coupling ratio",
    ),
    min_shared_revisions: int | None = typer.Option(
        None,
        "--min-shared-revisions",
        help="Override the profile's support floor",
    ),
    include_ci: bool | None = typer.Option(
        None,
        "--include-ci/--no-include-ci",
        help="Override whether the profile includes GitHub Actions evidence",
    ),
) -> None:
    """Review the selected change and emit at most three evidence-backed actions."""
    selector = _review_selector(base, staged, working_tree)
    try:
        result = run_change_review(
            repo,
            ChangeReviewRequest(
                selector=selector,
                profile=profile,
                days=days,
                min_coupling=min_coupling,
                min_shared_revisions=min_shared_revisions,
                include_ci=include_ci,
            ),
        )
    except BlackBoxUnlockError as error:
        console.print(f"[red]Error:[/red] {error}")
        raise typer.Exit(code=1) from error
    print(json.dumps(result.model_dump(mode="json"), indent=2))


@app.command()
def doctor(
    repo: Path = typer.Option(Path("."), "--repo", help="Repository root"),
) -> None:
    """Report whether local review dependencies are available."""
    resolved = repo.resolve()
    config_error: str | None = None
    try:
        config = load_project_config(resolved)
    except BlackBoxUnlockError as error:
        config = None
        config_error = str(error)
    checks = {
        "git": shutil.which("git") is not None,
        "repository": (resolved / ".git").exists(),
        "bbu": shutil.which("bbu") is not None,
        "bbu_mcp": shutil.which("bbu-mcp") is not None,
        "gh_optional": shutil.which("gh") is not None,
        "jq_required": False,
        "config": config is not None,
    }
    print(
        json.dumps(
            {
                "ok": checks["git"] and checks["repository"] and checks["config"],
                "checks": checks,
                "config": {
                    "profiles": sorted(config.profiles) if config is not None else [],
                    "path_role_rules": len(config.path_roles) if config is not None else 0,
                    "error": config_error,
                },
            },
            indent=2,
        )
    )


@app.command()
def validate(
    repos: list[Path] = typer.Option(
        [Path(".")], "--repo", help="Repository to validate (repeatable)"
    ),
    days: int = typer.Option(730, help="Total days of history (train + test halves)"),
    split: float = typer.Option(0.5, help="Fraction of the window forming the train half"),
    json_output: bool = typer.Option(False, "--json", help="Emit results as JSON"),
) -> None:
    """Validate the hotspot ranking against subsequent bug-fix commits.

    Splits history at a cutoff: files are ranked by hotspot score from the
    older half, then scored against bug-fix commits in the newer half.
    """
    import statistics

    from black_box_unlock import validation

    results = []
    for repo in repos:
        try:
            results.append(validation.validate_repo(repo, days=days, split=split))
        except BlackBoxUnlockError as e:
            console.print(f"[red]Error:[/red] {repo}: {e}")
    if json_output:
        print(json.dumps([r.model_dump(mode="json") for r in results], indent=2))
    else:
        for r in results:
            rho = f"{r.spearman:.2f}" if r.spearman is not None else "n/a"
            share = f"{r.top_decile_share:.0%}" if r.top_decile_share is not None else "n/a"
            coverage = f"{r.bugfix_coverage:.0%}" if r.bugfix_coverage is not None else "n/a"
            console.print(
                f"{r.repo}: files={r.file_count} rho={rho} "
                f"top-10% files take {share} of {r.test_bugfix_touches} bug-fix touches "
                f"(coverage {coverage})"
            )
        rhos = [r.spearman for r in results if r.spearman is not None]
        if len(rhos) > 1:
            console.print(f"median rho={statistics.median(rhos):.2f} across {len(rhos)} repos")
    if not results:
        raise typer.Exit(code=1)


@app.command()
def xray(
    file: str = typer.Argument(..., help="Repo-relative path of the file to X-Ray"),
    repo: Path = typer.Option(Path("."), "--repo", help="Repository root"),
    days: int = typer.Option(365, help="Days of history to analyze"),
    cap: int = typer.Option(200, "--cap", help="Maximum revisions to analyze"),
    min_coupling: float = typer.Option(
        0.3, "--min-coupling", help="Minimum function-pair coupling ratio to report"
    ),
) -> None:
    """Per-function churn for one file (Tornhill's X-Ray).

    Ranks the file's functions by revisions x indentation complexity and
    reports function pairs that change together. JSON to stdout.
    """
    from black_box_unlock.git import xray as xray_mod

    try:
        result = xray_mod.xray_file(repo, file, days=days, rev_cap=cap, min_coupling=min_coupling)
    except BlackBoxUnlockError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e
    print(json.dumps(result.model_dump(mode="json"), indent=2))


@app.command()
def version() -> None:  # [1a.2] Version info command
    """Show version information."""
    _version_callback(True)


if __name__ == "__main__":
    app()
