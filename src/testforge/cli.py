"""TestForge CLI - Main entry point."""

import sys
from pathlib import Path

import typer
from typing_extensions import Annotated

from testforge.config import ForgeConfig, load_config, save_config

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
    template: Annotated[
        str,
        typer.Option("--template", "-t", help="Template: mock or staging"),
    ] = "mock",
) -> None:
    """Scaffold a new config file from template."""
    config_path = Path(config)
    
    # Check if file exists
    if config_path.exists():
        overwrite = typer.confirm(
            f"Config file {config} already exists. Overwrite?",
            default=False,
        )
        if not overwrite:
            typer.echo("[!] Aborted.")
            raise typer.Exit(1)
    
    # Determine template source
    if template == "mock":
        template_path = Path(__file__).parent.parent.parent / "config" / "examples" / "mock-bot.yaml"
    elif template == "staging":
        template_path = Path(__file__).parent.parent.parent / "config" / "examples" / "staging-bot.yaml"
    else:
        typer.echo(f"[!] Unknown template: {template}. Use 'mock' or 'staging'.")
        raise typer.Exit(1)
    
    if not template_path.exists():
        typer.echo(f"[!] Template not found: {template_path}")
        raise typer.Exit(1)
    
    # Copy template
    config_path.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy(template_path, config_path)
    
    typer.echo(f"[*] Created config: {config} (from template: {template})")
    typer.echo(f"[*] Edit the file and set environment variables in .env")
    typer.echo(f"[*] Validate with: testforge config-validate {config}")


@app.command()
def config_validate(
    config: Annotated[
        str,
        typer.Argument(help="Path to config file"),
    ],
) -> None:
    """Validate config YAML."""
    typer.echo(f"[*] Validating config: {config}")
    
    try:
        cfg = load_config(config)
        typer.echo("[+] Configuration valid!")
        typer.echo(f"    Mode: {cfg.mode}")
        typer.echo(f"    Bot: {cfg.bot.name}")
        typer.echo(f"    LLM Provider: {cfg.llm.provider} ({cfg.llm.model})")
        typer.echo(f"    Cost Limits: ${cfg.cost_limits.per_scenario_max_usd}/scenario, ${cfg.cost_limits.per_run_max_usd}/run")
    except FileNotFoundError as e:
        typer.echo(f"[!] Error: {e}")
        raise typer.Exit(1)
    except ValueError as e:
        typer.echo(f"[!] Validation failed: {e}")
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"[!] Unexpected error: {e}")
        raise typer.Exit(1)


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
