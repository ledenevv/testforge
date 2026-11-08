"""TestForge CLI - Main entry point."""

import typer
from typing_extensions import Annotated

app = typer.Typer(
    name="testforge",
    help="E2E testing framework for ask-toby Telegram bot",
    add_completion=False,
)


@app.command()
def init(
    config: Annotated[
        str,
        typer.Option("--config", "-c", help="Path to save config file"),
    ] = "testforge.yaml",
) -> None:
    """Scaffold a new config file."""
    typer.echo(f"[*] Initializing config: {config}")
    typer.echo("[!] Command not implemented yet (Phase 0: M2)")


@app.command()
def config_validate(
    config: Annotated[
        str,
        typer.Argument(help="Path to config file"),
    ],
) -> None:
    """Validate config YAML."""
    typer.echo(f"[*] Validating config: {config}")
    typer.echo("[!] Command not implemented yet (Phase 0: M2)")


@app.command()
def plan(
    scenarios: Annotated[
        str,
        typer.Option("--scenarios", "-s", help="Scenarios directory or glob pattern"),
    ] = "fixtures/scenarios/*.yml",
) -> None:
    """Load and validate test scenarios."""
    typer.echo(f"[*] Loading scenarios: {scenarios}")
    typer.echo("[!] Command not implemented yet (Phase 0: M5)")


@app.command()
def run(
    scenario: Annotated[
        str,
        typer.Option("--scenario", "-s", help="Scenario file to run"),
    ],
    mode: Annotated[
        str,
        typer.Option("--mode", "-m", help="Execution mode: mock or real"),
    ] = "mock",
) -> None:
    """Execute test scenario(s)."""
    typer.echo(f"[*] Running scenario: {scenario} (mode: {mode})")
    typer.echo("[!] Command not implemented yet (Phase 0: M6)")


@app.command()
def verify(
    run_id: Annotated[
        str,
        typer.Option("--run-id", "-r", help="Run ID to verify (or 'latest')"),
    ] = "latest",
    llm_judge: Annotated[
        bool,
        typer.Option("--llm-judge", help="Run LLM-as-judge evaluation"),
    ] = False,
) -> None:
    """Validate run results."""
    judge_str = "with LLM-judge" if llm_judge else "without LLM-judge"
    typer.echo(f"[*] Verifying run: {run_id} ({judge_str})")
    typer.echo("[!] Command not implemented yet (Phase 0: M7, M9)")


@app.command()
def report(
    run_id: Annotated[
        str,
        typer.Option("--run-id", "-r", help="Run ID to report (or 'latest')"),
    ] = "latest",
    format: Annotated[
        str,
        typer.Option("--format", "-f", help="Report format: html or json"),
    ] = "html",
) -> None:
    """Generate test report."""
    typer.echo(f"[*] Generating {format} report for run: {run_id}")
    typer.echo("[!] Command not implemented yet (Phase 0: M11)")


@app.command()
def baseline_reset() -> None:
    """Clear baseline and re-establish on next run."""
    typer.echo("[*] Resetting baseline...")
    typer.echo("[!] Command not implemented yet (Phase 0: M10)")


@app.callback()
def main() -> None:
    """
    TestForge: E2E testing framework for ask-toby Telegram bot.
    
    Current status: Phase 0 - M1 complete (project setup)
    """
    pass


if __name__ == "__main__":
    app()
