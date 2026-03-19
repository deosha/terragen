"""
TerraGen Modifier - Modify existing Terraform infrastructure.
"""

import json
import subprocess
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from .config import MODIFY_SYSTEM_PROMPT
from .agent import TerraGenAgent, run_interactive_session

console = Console()


def read_terraform_files(infra_dir: Path) -> dict:
    """Read all Terraform files from a directory."""
    tf_files = {}
    for tf_file in infra_dir.rglob("*.tf"):
        # Skip .terraform directory
        if ".terraform" in str(tf_file):
            continue
        try:
            relative_path = tf_file.relative_to(infra_dir)
            content = tf_file.read_text()
            tf_files[str(relative_path)] = content
        except Exception as e:
            console.print(f"[yellow]Warning: Could not read {tf_file}: {e}[/yellow]")
    return tf_files


def read_state_file(infra_dir: Path) -> Optional[dict]:
    """Read Terraform state file (local or remote)."""
    # Try local state file first
    state_file = infra_dir / "terraform.tfstate"
    if state_file.exists():
        try:
            content = state_file.read_text()
            state = json.loads(content)
            console.print(f"[green]✓[/green] Found local terraform.tfstate")
            return state
        except Exception as e:
            console.print(f"[yellow]Warning: Could not parse state file: {e}[/yellow]")

    # Try pulling from remote backend
    try:
        result = subprocess.run(
            ["terraform", "state", "pull"],
            cwd=infra_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            state = json.loads(result.stdout)
            console.print(f"[green]✓[/green] Pulled state from remote backend")
            return state
    except subprocess.TimeoutExpired:
        console.print("[yellow]Warning: Timeout pulling remote state[/yellow]")
    except json.JSONDecodeError:
        pass
    except FileNotFoundError:
        console.print("[yellow]Warning: terraform CLI not found[/yellow]")
    except Exception as e:
        console.print(f"[yellow]Warning: Could not pull remote state: {e}[/yellow]")

    return None


def get_git_info(infra_dir: Path) -> dict:
    """Get git repository information."""
    git_info = {
        "is_repo": False,
        "branch": None,
        "last_commit": None,
        "uncommitted_changes": False,
        "recent_commits": [],
    }

    try:
        # Check if it's a git repo
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=infra_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return git_info

        git_info["is_repo"] = True

        # Get current branch
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=infra_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            git_info["branch"] = result.stdout.strip()

        # Get last commit
        result = subprocess.run(
            ["git", "log", "-1", "--format=%h %s (%cr)"],
            cwd=infra_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            git_info["last_commit"] = result.stdout.strip()

        # Check for uncommitted changes
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=infra_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            git_info["uncommitted_changes"] = bool(result.stdout.strip())

        # Get recent commits
        result = subprocess.run(
            ["git", "log", "-5", "--format=%h %s"],
            cwd=infra_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            git_info["recent_commits"] = result.stdout.strip().split("\n")

    except FileNotFoundError:
        console.print("[yellow]Warning: git CLI not found[/yellow]")
    except Exception as e:
        console.print(f"[yellow]Warning: Could not get git info: {e}[/yellow]")

    return git_info


def summarize_state(state: dict) -> str:
    """Summarize Terraform state into readable format."""
    if not state:
        return "No state file found"

    resources = state.get("resources", [])
    if not resources:
        return "No resources in state"

    summary = []
    resource_counts = {}

    for resource in resources:
        resource_type = resource.get("type", "unknown")
        resource_counts[resource_type] = resource_counts.get(resource_type, 0) + 1

    summary.append(f"Total resources: {len(resources)}")
    summary.append("\nResource types:")
    for rtype, count in sorted(resource_counts.items()):
        summary.append(f"  - {rtype}: {count}")

    # Get some key resource details (filter sensitive data)
    summary.append("\nKey resources:")
    for resource in resources[:10]:  # Limit to first 10
        rtype = resource.get("type", "unknown")
        name = resource.get("name", "unknown")
        summary.append(f"  - {rtype}.{name}")

    if len(resources) > 10:
        summary.append(f"  ... and {len(resources) - 10} more")

    return "\n".join(summary)


def create_branch(infra_dir: Path, branch_name: str) -> bool:
    """Create a new git branch."""
    try:
        result = subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=infra_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            console.print(f"[green]✓[/green] Created branch: {branch_name}")
            return True
        else:
            console.print(f"[red]✗[/red] Failed to create branch: {result.stderr}")
            return False
    except Exception as e:
        console.print(f"[red]✗[/red] Error creating branch: {e}")
        return False


def commit_changes(infra_dir: Path, message: str) -> bool:
    """Commit all changes in the directory."""
    try:
        # Stage all changes
        result = subprocess.run(
            ["git", "add", "-A"], cwd=infra_dir, capture_output=True, text=True
        )
        if result.returncode != 0:
            console.print(f"[red]✗[/red] Failed to stage changes: {result.stderr}")
            return False

        # Commit
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=infra_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            console.print(f"[green]✓[/green] Committed: {message}")
            return True
        else:
            console.print(f"[red]✗[/red] Failed to commit: {result.stderr}")
            return False
    except Exception as e:
        console.print(f"[red]✗[/red] Error committing: {e}")
        return False


def push_branch(infra_dir: Path, branch_name: str) -> bool:
    """Push branch to remote."""
    try:
        result = subprocess.run(
            ["git", "push", "-u", "origin", branch_name],
            cwd=infra_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            console.print(f"[green]✓[/green] Pushed branch to origin")
            return True
        else:
            console.print(f"[red]✗[/red] Failed to push: {result.stderr}")
            return False
    except Exception as e:
        console.print(f"[red]✗[/red] Error pushing: {e}")
        return False


def create_pull_request(infra_dir: Path, title: str, body: str) -> Optional[str]:
    """Create a pull request using GitHub CLI."""
    try:
        result = subprocess.run(
            ["gh", "pr", "create", "--title", title, "--body", body],
            cwd=infra_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            pr_url = result.stdout.strip()
            console.print(f"[green]✓[/green] Created PR: {pr_url}")
            return pr_url
        else:
            console.print(f"[red]✗[/red] Failed to create PR: {result.stderr}")
            return None
    except FileNotFoundError:
        console.print(
            "[yellow]Warning: GitHub CLI (gh) not found. Install with: brew install gh[/yellow]"
        )
        return None
    except Exception as e:
        console.print(f"[red]✗[/red] Error creating PR: {e}")
        return None


def modify_infrastructure(
    prompt: str, infra_dir: Path, chat_mode: bool = False
) -> None:
    """Modify existing Terraform infrastructure."""

    console.print(
        Panel.fit(
            "[bold blue]TerraGen - Modify Existing Infrastructure[/bold blue]",
            title="Modify Mode",
        )
    )

    # Read existing infrastructure
    console.print("\n[yellow]Reading infrastructure...[/yellow]")

    # Read .tf files
    tf_files = read_terraform_files(infra_dir)
    if not tf_files:
        console.print("[red]Error: No Terraform files found in directory[/red]")
        return

    console.print(f"[green]✓[/green] Found {len(tf_files)} .tf files")

    # Read state file
    state = read_state_file(infra_dir)
    state_summary = summarize_state(state) if state else "No state file found"

    # Get git info
    git_info = get_git_info(infra_dir)
    is_git_repo = git_info["is_repo"]

    if is_git_repo:
        console.print(
            f"[green]✓[/green] Git repo detected (branch: {git_info['branch']}, last commit: {git_info['last_commit']})"
        )
        if git_info["uncommitted_changes"]:
            console.print(
                "[red]Error: You have uncommitted changes. Please commit or stash them first.[/red]"
            )
            return
    else:
        console.print(
            "[yellow]![/yellow] Not a git repository - changes will be made directly"
        )

    # Show analysis
    console.print(
        Panel.fit(
            f"[bold]Infrastructure Analysis[/bold]\n\n"
            f"[green]Terraform files:[/green] {len(tf_files)}\n"
            f"[green]Resources deployed:[/green] {len(state.get('resources', [])) if state else 'Unknown'}\n"
            f"[green]Git repo:[/green] {'Yes' if is_git_repo else 'No'}\n"
            f"[green]Git branch:[/green] {git_info['branch'] or 'N/A'}",
            title="Current State",
        )
    )

    branch_name = None

    # For git repos: create branch first
    if is_git_repo:
        console.print("\n[yellow]Step 1: Creating branch...[/yellow]")
        branch_name = "terragen/" + "-".join(prompt.lower().split()[:4])
        branch_name = "".join(
            c if c.isalnum() or c == "-" or c == "/" else "-" for c in branch_name
        )

        if not create_branch(infra_dir, branch_name):
            console.print("[red]Failed to create branch. Aborting.[/red]")
            return
    else:
        # For local projects: ask for confirmation
        if not Confirm.ask(
            "\n[yellow]Proceed with modifications?[/yellow]", default=True
        ):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    # Build context for Claude
    existing_code_context = "\n## Existing Terraform Code\n"
    for filename, content in tf_files.items():
        # Truncate large files
        if len(content) > 3000:
            content = content[:3000] + "\n... (truncated)"
        existing_code_context += f"\n### {filename}:\n```hcl\n{content}\n```\n"

    state_context = f"\n## Current Infrastructure State\n{state_summary}\n"

    # Build the modification prompt
    full_prompt = f"""## Modification Request
{prompt}

## Working Directory
{infra_dir}

{existing_code_context}

{state_context}

## Instructions
1. First, READ the existing files to understand the current structure
2. PRESERVE existing resources and patterns - do NOT recreate from scratch
3. Only ADD or MODIFY what's needed for the new requirements
4. Keep the same code style, naming conventions, and tagging patterns
5. Update variables.tf if new variables are needed
6. Update outputs.tf if new outputs are needed
7. After making changes, validate:
   - cd {infra_dir} && terraform fmt -recursive
   - terraform validate
8. If validation fails, fix the issues
9. Summarize what was changed/added

IMPORTANT: Use absolute paths like {infra_dir}/main.tf when modifying files.
"""

    # Generate modifications
    step_num = 2 if is_git_repo else 1
    console.print(f"\n[yellow]Step {step_num}: Generating modifications...[/yellow]\n")

    if chat_mode:
        run_interactive_session(full_prompt, infra_dir, MODIFY_SYSTEM_PROMPT)
    else:
        agent = TerraGenAgent(infra_dir, MODIFY_SYSTEM_PROMPT)
        agent.chat(full_prompt)

    # For git repos, check if there are changes
    if is_git_repo:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=infra_dir,
            capture_output=True,
            text=True,
        )
        if not result.stdout.strip():
            console.print(
                "[yellow]No changes were made to the infrastructure.[/yellow]"
            )
            # Switch back to original branch
            subprocess.run(["git", "checkout", "-"], cwd=infra_dir, capture_output=True)
            subprocess.run(
                ["git", "branch", "-D", branch_name], cwd=infra_dir, capture_output=True
            )
            return

        # Show modified files
        console.print("\n[bold]Modified files:[/bold]")
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                console.print(f"  {line}")

    # Run terraform plan to show only the changes
    step_num = 3 if is_git_repo else 2
    console.print(f"\n[yellow]Step {step_num}: Running terraform plan...[/yellow]\n")
    plan_summary = ""
    try:
        # Initialize if needed
        subprocess.run(
            ["terraform", "init", "-backend=false"],
            cwd=infra_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Run plan
        result = subprocess.run(
            ["terraform", "plan", "-no-color"],
            cwd=infra_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            plan_output = result.stdout
            lines = plan_output.split("\n")
            changes = []
            summary_line = ""

            for line in lines:
                if line.strip().startswith("# ") and (
                    "will be" in line or "must be" in line
                ):
                    changes.append(line)
                elif line.strip().startswith("Plan:"):
                    summary_line = line.strip()
                    plan_summary = summary_line

            if changes:
                console.print(
                    Panel.fit(
                        "[bold]Planned Infrastructure Changes[/bold]\n\n"
                        + "\n".join(changes[:20])
                        + ("\n..." if len(changes) > 20 else "")
                        + (f"\n\n[bold]{summary_line}[/bold]" if summary_line else ""),
                        title="Terraform Plan",
                    )
                )
            elif "No changes" in plan_output:
                console.print("[green]No infrastructure changes detected.[/green]")
                plan_summary = "No changes"
        else:
            console.print(f"[yellow]Plan warning: {result.stderr[:300]}[/yellow]")

    except Exception as e:
        console.print(f"[yellow]Could not run terraform plan: {e}[/yellow]")

    # For git repos: commit and create PR
    if is_git_repo:
        # Step 4: Commit changes
        console.print("\n[yellow]Step 4: Committing changes...[/yellow]")
        commit_msg = f"TerraGen: {prompt[:50]}"
        if not commit_changes(infra_dir, commit_msg):
            console.print("[red]Failed to commit changes.[/red]")
            return

        # Step 5: Push and create PR
        console.print("\n[yellow]Step 5: Creating pull request...[/yellow]")
        if not push_branch(infra_dir, branch_name):
            console.print("[red]Failed to push branch. You can push manually.[/red]")
        else:
            pr_body = f"""## Summary
{prompt}

## Terraform Plan
```
{plan_summary or 'See terraform plan output'}
```

## Checklist
- [ ] Review Terraform plan output
- [ ] Verify security implications
- [ ] Test in non-production environment first
- [ ] Get approval from infrastructure team

---
*Generated by TerraGen AI*
"""
            pr_url = create_pull_request(infra_dir, f"TerraGen: {prompt[:50]}", pr_body)

            if pr_url:
                console.print(
                    Panel.fit(
                        f"[bold green]Pull Request Created![/bold green]\n\n"
                        f"[green]PR URL:[/green] {pr_url}\n"
                        f"[green]Branch:[/green] {branch_name}\n\n"
                        f"[yellow]Next steps:[/yellow]\n"
                        f"  1. Review the PR\n"
                        f"  2. Run terraform plan in CI\n"
                        f"  3. Get approval and merge",
                        title="Success",
                    )
                )
            else:
                console.print(
                    Panel.fit(
                        f"[bold yellow]Changes pushed to branch[/bold yellow]\n\n"
                        f"[green]Branch:[/green] {branch_name}\n\n"
                        f"[yellow]Create PR manually or install GitHub CLI:[/yellow]\n"
                        f"  brew install gh && gh auth login",
                        title="Done",
                    )
                )
    else:
        # For local projects: show success
        console.print(
            Panel.fit(
                f"[bold green]Modification Complete![/bold green]\n\n"
                f"[green]Modified directory:[/green] {infra_dir}\n\n"
                f"[yellow]Next steps:[/yellow]\n"
                f"  cd {infra_dir}\n"
                f"  terraform plan  # Review changes\n"
                f"  terraform apply",
                title="Success",
            )
        )
