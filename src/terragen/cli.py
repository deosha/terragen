"""
TerraGen CLI - Command line interface.
"""

import asyncio
import os
import shutil
import subprocess
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

# Load .env file before anything else
from dotenv import load_dotenv

load_dotenv()

from .config import get_default_region
from .generator import (
    generate_terraform,
    generate_terraform_pipeline,
    AWS_CREDS_AVAILABLE,
)
from .modifier import modify_infrastructure
from .questions import ask_clarifying_questions, ask_backend_config

console = Console()


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """TerraGen - AI-powered Terraform code generator"""
    pass


@cli.command()
@click.argument("prompt")
@click.option(
    "--output",
    "-o",
    default="./output",
    help="Output directory (e.g., ./infra, /tmp/tf)",
)
@click.option(
    "--provider",
    "-p",
    default="aws",
    type=click.Choice(["aws", "gcp", "azure"]),
    help="Cloud provider: aws, gcp, azure",
)
@click.option(
    "--region",
    "-r",
    default=None,
    help="Cloud region (default: us-east-1 for AWS, us-central1 for GCP, eastus for Azure)",
)
@click.option(
    "--interactive",
    "-i",
    is_flag=True,
    help="Ask clarifying questions before generation",
)
@click.option(
    "--learn-from",
    "-l",
    type=click.Path(exists=True),
    help="Path to existing Terraform repo to learn patterns",
)
@click.option(
    "--chat",
    "-c",
    is_flag=True,
    help="Continue conversation for code refinement after generation",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip confirmation prompt and proceed automatically",
)
@click.option(
    "--backend",
    "-b",
    type=click.Choice(["s3", "gcs", "azurerm", "remote", "local"]),
    default="local",
    help="State backend: local, s3, gcs, azurerm, remote (Terraform Cloud)",
)
@click.option(
    "--modify",
    "-m",
    type=click.Path(exists=True),
    help="Path to existing infrastructure repo to modify",
)
@click.option(
    "--skip-clarify",
    is_flag=True,
    help="Skip clarification questions (auto-detect mode)",
)
@click.option("--skip-cost", is_flag=True, help="Skip cost estimation")
@click.option(
    "--max-security-fixes",
    default=3,
    type=int,
    help="Maximum security fix attempts (default: 3)",
)
@click.option(
    "--pipeline/--no-pipeline",
    default=True,
    help="Use multi-agent pipeline (default: True)",
)
def generate(
    prompt: str,
    output: str,
    provider: str,
    region: str,
    interactive: bool,
    learn_from: str,
    chat: bool,
    yes: bool,
    backend: str,
    modify: str,
    skip_clarify: bool,
    skip_cost: bool,
    max_security_fixes: int,
    pipeline: bool,
):
    """Generate Terraform code from natural language.

    The multi-agent pipeline includes:
    - Clarification (auto-detects if questions needed)
    - Code Generation
    - Validation (terraform fmt/init/validate)
    - Security Scanning (tfsec, checkov, conftest)
    - Automatic Fix Loop (up to 3 attempts)
    - Cost Estimation (infracost)

    Examples:
        terragen generate "Create an S3 bucket with versioning"
        terragen generate "Create an EKS cluster" --skip-clarify
        terragen generate "Create a VPC with public/private subnets" --skip-cost
        terragen generate "Create RDS PostgreSQL" --max-security-fixes 5
    """

    # Set default region based on provider if not specified
    if region is None:
        region = get_default_region(provider)

    # Check if at least one LLM provider API key is available
    has_api_key = any(
        [
            os.environ.get("ANTHROPIC_API_KEY"),
            os.environ.get("XAI_API_KEY"),
            os.environ.get("OPENAI_API_KEY"),
        ]
    )
    if not has_api_key:
        console.print("[red]Error: No LLM API key configured[/red]")
        console.print(
            "Set at least one of: ANTHROPIC_API_KEY, XAI_API_KEY, OPENAI_API_KEY"
        )
        return

    # If --modify is specified, use modification mode
    if modify:
        modify_path = Path(modify).resolve()
        modify_infrastructure(prompt, modify_path, chat)
        return

    clarifications = None
    # Only ask interactive questions if --interactive and not --skip-clarify
    if interactive and not skip_clarify:
        clarifications = ask_clarifying_questions(prompt)
        provider = clarifications.get("provider", provider)
        region = clarifications.get("region", region)

    output_path = Path(output).resolve()
    learn_path = Path(learn_from).resolve() if learn_from else None

    # Configure backend if not local
    backend_config = None
    if backend != "local":
        backend_config = ask_backend_config(backend, provider, region)

    # Show summary and ask for confirmation unless --yes flag
    if not yes:
        while True:
            backend_display = (
                backend
                if backend == "local"
                else f"{backend} ({backend_config.get('bucket', backend_config.get('organization', ''))})"
            )
            pipeline_status = (
                "[green]Enabled[/green]" if pipeline else "[dim]Disabled[/dim]"
            )

            console.print(
                Panel.fit(
                    f"[bold blue]TerraGen - Generation Summary[/bold blue]\n\n"
                    f"[green]Request:[/green] {prompt}\n"
                    f"[green]Provider:[/green] {provider}\n"
                    f"[green]Region:[/green] {region}\n"
                    f"[green]Output:[/green] {output_path}\n"
                    f"[green]Backend:[/green] {backend_display}\n"
                    f"[green]AWS Credentials:[/green] {'Available' if AWS_CREDS_AVAILABLE else 'Not found'}\n"
                    f"[green]Learn from:[/green] {learn_path or 'None'}\n"
                    f"[green]Chat mode:[/green] {'Yes' if chat else 'No'}\n"
                    f"[green]Multi-Agent Pipeline:[/green] {pipeline_status}\n"
                    f"[green]Skip Clarify:[/green] {'Yes' if skip_clarify else 'No (auto-detect)'}\n"
                    f"[green]Skip Cost:[/green] {'Yes' if skip_cost else 'No'}\n"
                    f"[green]Max Security Fixes:[/green] {max_security_fixes}",
                    title="Confirm",
                )
            )

            console.print("\n[bold]Options:[/bold]")
            console.print("  [green]y[/green] - Proceed with generation")
            console.print("  [red]n[/red] - Cancel")
            console.print("  [yellow]m[/yellow] - Modify requirements")

            choice = Prompt.ask("Select", choices=["y", "n", "m"], default="y")

            if choice == "y":
                break
            elif choice == "n":
                console.print("[yellow]Generation cancelled.[/yellow]")
                return
            elif choice == "m":
                console.print("\n[bold]Current requirements:[/bold]")
                console.print(f"  {prompt}\n")
                new_prompt = Prompt.ask(
                    "[yellow]Enter new/modified requirements[/yellow]"
                )
                if new_prompt.strip():
                    prompt = new_prompt.strip()
                console.print()  # Blank line before showing updated summary

    # Use pipeline or legacy generator
    if pipeline:
        # Run the multi-agent pipeline
        asyncio.run(
            generate_terraform_pipeline(
                prompt=prompt,
                output_dir=output_path,
                provider=provider,
                region=region,
                clarifications=clarifications,
                learn_from=learn_path,
                chat_mode=chat,
                backend_config=backend_config,
                skip_clarify=skip_clarify,
                skip_cost=skip_cost,
                max_security_fixes=max_security_fixes,
            )
        )
    else:
        # Use legacy single-agent generator
        generate_terraform(
            prompt,
            output_path,
            provider,
            region,
            clarifications,
            learn_path,
            chat,
            backend_config,
        )


@cli.command()
@click.argument("directory", type=click.Path(exists=True), default=".")
def validate(directory: str):
    """Validate Terraform code in directory."""

    console.print(f"[yellow]Validating Terraform in {directory}...[/yellow]\n")

    checks = [
        ("Format Check", "terraform fmt -check -recursive"),
        ("Initialize", "terraform init -backend=false"),
        ("Validate", "terraform validate"),
    ]

    if shutil.which("tflint"):
        checks.append(("TFLint", "tflint"))
    if shutil.which("tfsec"):
        checks.append(("TFSec", "tfsec ."))
    if shutil.which("checkov"):
        checks.append(("Checkov", "checkov -d . --quiet"))
    if shutil.which("conftest"):
        # Check if policies directory exists
        policies_dir = Path(__file__).parent.parent.parent / "policies"
        if policies_dir.exists():
            checks.append(("Conftest", f"conftest test --policy {policies_dir} *.tf"))

    for name, cmd in checks:
        result = subprocess.run(
            f"cd {directory} && {cmd}", shell=True, capture_output=True, text=True
        )
        if result.returncode == 0:
            console.print(f"[green]✓ {name}[/green]")
        else:
            console.print(f"[red]✗ {name}[/red]")
            if result.stderr:
                console.print(result.stderr[:500])


@cli.command()
@click.argument("directory", type=click.Path(exists=True), default=".")
def cost(directory: str):
    """Estimate infrastructure costs with Infracost."""

    if not shutil.which("infracost"):
        console.print("[red]Infracost not installed.[/red]")
        console.print("Install: brew install infracost")
        return

    console.print(f"[yellow]Estimating costs for {directory}...[/yellow]\n")

    result = subprocess.run(
        f"cd {directory} && infracost breakdown --path . --format table",
        shell=True,
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        console.print(result.stdout)
    else:
        console.print(f"[red]Error: {result.stderr}[/red]")


@cli.command()
@click.argument("directory", type=click.Path(exists=True), default=".")
def security(directory: str):
    """Run security scans on Terraform code."""

    console.print(f"[yellow]Running security scans in {directory}...[/yellow]\n")

    scans = []

    if shutil.which("tfsec"):
        scans.append(("tfsec", "tfsec . --soft-fail"))
    else:
        console.print("[dim]tfsec not installed (brew install tfsec)[/dim]")

    if shutil.which("checkov"):
        scans.append(("Checkov", "checkov -d . --soft-fail"))
    else:
        console.print("[dim]checkov not installed (brew install checkov)[/dim]")

    if shutil.which("conftest"):
        policies_dir = Path(__file__).parent.parent.parent / "policies"
        if policies_dir.exists():
            scans.append(("Conftest", f"conftest test --policy {policies_dir} *.tf"))
        else:
            console.print("[dim]No policies directory found for conftest[/dim]")
    else:
        console.print("[dim]conftest not installed (brew install conftest)[/dim]")

    if not scans:
        console.print("[red]No security scanners installed.[/red]")
        console.print("Install with: brew install tfsec checkov conftest")
        return

    console.print()
    for name, cmd in scans:
        console.print(f"[bold cyan]>>> {name}[/bold cyan]")
        result = subprocess.run(
            f"cd {directory} && {cmd}", shell=True, capture_output=True, text=True
        )
        if result.stdout:
            console.print(result.stdout)
        if result.stderr:
            console.print(result.stderr)
        console.print()


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
