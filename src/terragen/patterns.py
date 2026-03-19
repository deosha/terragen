"""
TerraGen Patterns - Learn patterns from existing Terraform repos.
"""

from pathlib import Path

from rich.console import Console

console = Console()


def learn_patterns_from_repo(repo_path: Path) -> str:
    """Scan existing Terraform repo and extract patterns."""
    console.print(f"\n[yellow]Learning patterns from {repo_path}...[/yellow]")

    tf_files = list(repo_path.rglob("*.tf"))
    if not tf_files:
        console.print("[red]No .tf files found[/red]")
        return ""

    console.print(f"[dim]Found {len(tf_files)} Terraform files[/dim]")

    patterns = ["## Patterns from Existing Repo\nFollow these conventions:\n"]

    # Sample key files
    key_files = ["providers.tf", "variables.tf", "outputs.tf", "main.tf"]
    for tf_file in tf_files[:20]:  # Limit scanning
        if tf_file.name in key_files:
            try:
                content = tf_file.read_text()
                lines = content.split("\n")[:50]  # First 50 lines
                patterns.append(
                    f"\n### {tf_file.name}:\n```hcl\n{chr(10).join(lines)}\n```\n"
                )
            except Exception:
                pass

    return "".join(patterns)
