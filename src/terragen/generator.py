"""
TerraGen Generator - Main Terraform generation logic.
"""

import os
import shutil
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel

from .config import SYSTEM_PROMPT
from .agent import run_agent, run_interactive_session
from .questions import build_clarification_context, build_backend_context
from .patterns import learn_patterns_from_repo

console = Console()


def has_aws_credentials() -> bool:
    """Check if AWS credentials are available."""
    # Check environment variables
    if os.environ.get('AWS_ACCESS_KEY_ID') and os.environ.get('AWS_SECRET_ACCESS_KEY'):
        return True
    # Check AWS credentials file
    aws_creds = Path.home() / '.aws' / 'credentials'
    if aws_creds.exists():
        return True
    # Check AWS config (for SSO/profiles)
    aws_config = Path.home() / '.aws' / 'config'
    if aws_config.exists():
        return True
    return False


AWS_CREDS_AVAILABLE = has_aws_credentials()


def generate_terraform(
    prompt: str,
    output_dir: Path,
    provider: str = "aws",
    region: str = "us-east-1",
    clarifications: Optional[dict] = None,
    learn_from: Optional[Path] = None,
    chat_mode: bool = False,
    backend_config: Optional[dict] = None
) -> None:
    """Generate Terraform code using Anthropic API (legacy single-agent mode)."""

    # Ensure output directory exists
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    mode_text = "[bold magenta]Chat Mode[/bold magenta] - " if chat_mode else ""
    console.print(Panel.fit(
        f"{mode_text}[bold blue]TerraGen - AI Terraform Generator[/bold blue]\n\n"
        f"[green]Prompt:[/green] {prompt}\n"
        f"[green]Provider:[/green] {provider}\n"
        f"[green]Region:[/green] {region}\n"
        f"[green]Output:[/green] {output_dir}",
        title="Configuration"
    ))

    # Build context
    clarification_context = build_clarification_context(clarifications) if clarifications else ""
    learned_patterns = learn_patterns_from_repo(learn_from) if learn_from else ""
    backend_context = build_backend_context(backend_config) if backend_config else ""

    # Build plan instruction based on AWS creds availability
    plan_instruction = ""
    if AWS_CREDS_AVAILABLE:
        plan_instruction = f"\n   - terraform plan (AWS credentials detected)"
    else:
        plan_instruction = "\n   - Skip terraform plan (no AWS credentials)"

    full_prompt = f'''## User Request
{prompt}

## Configuration
- Cloud Provider: {provider}
- Region: {region}
- Output Directory: {output_dir}
- AWS Credentials: {"Available" if AWS_CREDS_AVAILABLE else "Not found"}
{clarification_context}

{learned_patterns}
{backend_context}

## Instructions
1. Create all Terraform files in {output_dir}/ using absolute paths
2. Include GitHub Actions workflows for CI/CD
3. After creating files, validate:
   - cd {output_dir} && terraform fmt -recursive
   - terraform init -backend=false
   - terraform validate{plan_instruction}
4. If validation fails, fix the issues and retry
5. Generate a README.md
6. IMPORTANT - Review & Verify:
   - Re-read the user request above
   - List each requirement from the request
   - Check if EACH requirement is implemented in the generated code
   - If any requirement is missing, add it and re-validate
   - Report: "✓ Requirement X implemented in resource Y"

Use absolute paths like {output_dir}/main.tf when creating files.
Start by creating {output_dir}/providers.tf and {output_dir}/versions.tf first.'''

    console.print("\n[yellow]Generating Terraform code...[/yellow]\n")

    if chat_mode:
        # Interactive mode - allows continuous refinement
        run_interactive_session(full_prompt, output_dir)
    else:
        # Single-shot mode
        result = run_agent(full_prompt, output_dir)

    console.print(Panel.fit(
        f"[bold green]Generation Complete![/bold green]\n\n"
        f"[green]Files created in:[/green] {output_dir}\n\n"
        f"[yellow]Next steps:[/yellow]\n"
        f"  cd {output_dir}\n"
        f"  terraform init\n"
        f"  terraform plan\n"
        f"  terraform apply",
        title="Success"
    ))


async def generate_terraform_pipeline(
    prompt: str,
    output_dir: Path,
    provider: str = "aws",
    region: str = "us-east-1",
    clarifications: Optional[dict] = None,
    learn_from: Optional[Path] = None,
    chat_mode: bool = False,
    backend_config: Optional[dict] = None,
    skip_clarify: bool = False,
    skip_cost: bool = False,
    max_security_fixes: int = 3,
) -> None:
    """Generate Terraform code using the multi-agent pipeline.

    This is the new pipeline-based generator that includes:
    - Clarification (auto-detect mode)
    - Code generation
    - Validation (terraform fmt/init/validate)
    - Security scanning (tfsec, checkov, conftest)
    - Automatic fix loop for security issues
    - Cost estimation (infracost)

    Args:
        prompt: User's infrastructure request.
        output_dir: Directory to write generated files.
        provider: Cloud provider (aws, gcp, azure).
        region: Cloud region.
        clarifications: Pre-collected clarification answers.
        learn_from: Path to existing repo for pattern learning.
        chat_mode: Enable interactive chat mode.
        backend_config: Backend configuration dict.
        skip_clarify: Skip clarification questions.
        skip_cost: Skip cost estimation.
        max_security_fixes: Maximum security fix attempts.
    """
    from .agents.context import PipelineContext
    from .agents.orchestrator import PipelineOrchestrator

    # Create pipeline context
    context = PipelineContext(
        user_prompt=prompt,
        provider=provider,
        region=region,
        output_dir=output_dir,
        skip_clarify=skip_clarify,
        skip_cost=skip_cost,
        max_security_fix_attempts=max_security_fixes,
        chat_mode=chat_mode,
        backend_config=backend_config,
        learn_from=learn_from,
    )

    # Pre-populate clarifications if provided
    if clarifications:
        context.clarifications = clarifications

    # Run the orchestrator
    orchestrator = PipelineOrchestrator()
    await orchestrator.run(context)

    # Return the context for API use
    return context
