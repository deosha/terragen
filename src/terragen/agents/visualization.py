"""Rich-based visualizations for the agent pipeline."""

from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskID
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.layout import Layout
from rich.style import Style

from terragen.agents.base import (
    AgentStatus,
    CostBreakdown,
    IssueSeverity,
    SecurityIssue,
    ValidationError,
)
from terragen.agents.context import PipelineContext


# Severity color mapping
SEVERITY_COLORS = {
    IssueSeverity.CRITICAL: "bold red",
    IssueSeverity.HIGH: "red",
    IssueSeverity.MEDIUM: "yellow",
    IssueSeverity.LOW: "blue",
    IssueSeverity.INFO: "dim",
}

# Status color mapping
STATUS_COLORS = {
    AgentStatus.PENDING: "dim",
    AgentStatus.RUNNING: "yellow",
    AgentStatus.SUCCESS: "green",
    AgentStatus.FAILED: "red",
    AgentStatus.SKIPPED: "dim cyan",
}

# Status icons
STATUS_ICONS = {
    AgentStatus.PENDING: "○",
    AgentStatus.RUNNING: "◐",
    AgentStatus.SUCCESS: "✓",
    AgentStatus.FAILED: "✗",
    AgentStatus.SKIPPED: "⊘",
}


def create_security_issues_table(
    issues: list[SecurityIssue], title: str = "Security Issues"
) -> Table:
    """Create a Rich table displaying security issues.

    Args:
        issues: List of security issues to display.
        title: Table title.

    Returns:
        Rich Table object.
    """
    table = Table(title=title, show_header=True, header_style="bold magenta")

    table.add_column("Severity", style="bold", width=10)
    table.add_column("Rule ID", style="cyan", width=15)
    table.add_column("Description", width=40)
    table.add_column("File:Line", style="dim", width=20)
    table.add_column("Scanner", style="dim", width=10)

    # Sort by severity (CRITICAL first)
    severity_order = {
        IssueSeverity.CRITICAL: 0,
        IssueSeverity.HIGH: 1,
        IssueSeverity.MEDIUM: 2,
        IssueSeverity.LOW: 3,
        IssueSeverity.INFO: 4,
    }
    sorted_issues = sorted(issues, key=lambda x: severity_order.get(x.severity, 5))

    for issue in sorted_issues:
        severity_style = SEVERITY_COLORS.get(issue.severity, "")
        table.add_row(
            Text(issue.severity.value, style=severity_style),
            issue.rule_id,
            (
                issue.description[:40] + "..."
                if len(issue.description) > 40
                else issue.description
            ),
            f"{issue.file_path}:{issue.line_number}",
            issue.scanner,
        )

    return table


def create_validation_errors_table(errors: list[ValidationError]) -> Table:
    """Create a Rich table displaying validation errors.

    Args:
        errors: List of validation errors to display.

    Returns:
        Rich Table object.
    """
    table = Table(title="Validation Errors", show_header=True, header_style="bold red")

    table.add_column("Type", style="bold", width=10)
    table.add_column("Message", width=50)
    table.add_column("File:Line", style="dim", width=25)

    for error in errors:
        location = ""
        if error.file_path:
            location = error.file_path
            if error.line_number:
                location += f":{error.line_number}"

        table.add_row(
            error.error_type.upper(),
            error.message[:50] + "..." if len(error.message) > 50 else error.message,
            location,
        )

    return table


def create_cost_breakdown_table(
    costs: list[CostBreakdown],
    total_monthly: float = 0.0,
    total_yearly: float = 0.0,
) -> Table:
    """Create a Rich table displaying infrastructure cost estimates.

    Args:
        costs: List of cost breakdowns by resource.
        total_monthly: Total monthly cost.
        total_yearly: Total yearly cost.

    Returns:
        Rich Table object.
    """
    table = Table(
        title="Infrastructure Cost Estimate",
        show_header=True,
        header_style="bold green",
    )

    table.add_column("Resource", style="bold", width=25)
    table.add_column("Type", style="cyan", width=15)
    table.add_column("Monthly", justify="right", width=12)
    table.add_column("Yearly", justify="right", width=12)

    for cost in costs:
        table.add_row(
            cost.resource_name,
            cost.resource_type,
            f"${cost.monthly_cost:,.2f}",
            f"${cost.yearly_cost:,.2f}",
        )

    # Add separator and totals
    table.add_row("", "", "", "", style="dim")
    table.add_row(
        Text("TOTAL", style="bold"),
        "",
        Text(f"${total_monthly:,.2f}", style="bold green"),
        Text(f"${total_yearly:,.2f}", style="bold green"),
    )

    return table


def create_pipeline_status_panel(
    agent_statuses: dict[str, AgentStatus],
    current_agent: str = "",
    fix_attempt: int = 0,
    max_attempts: int = 3,
) -> Panel:
    """Create a panel showing the pipeline status.

    Args:
        agent_statuses: Dict mapping agent names to their statuses.
        current_agent: Name of the currently running agent.
        fix_attempt: Current fix attempt number.
        max_attempts: Maximum fix attempts allowed.

    Returns:
        Rich Panel object.
    """
    lines = []

    agent_order = [
        ("Clarification", "ClarificationAgent"),
        ("Code Generation", "CodeGenerationAgent"),
        ("Validation", "ValidationAgent"),
        ("Security (tfsec)", "SecurityAgent"),
        ("Checkov", "CheckovAgent"),
        ("Policy (OPA)", "PolicyAgent"),
        ("Cost Estimation", "CostEstimationAgent"),
    ]

    for display_name, agent_name in agent_order:
        status = agent_statuses.get(agent_name, AgentStatus.PENDING)
        icon = STATUS_ICONS.get(status, "?")
        color = STATUS_COLORS.get(status, "")

        # Highlight current agent
        if agent_name == current_agent:
            line = f"[bold {color}]{icon} {display_name} ← Running[/bold {color}]"
        else:
            line = f"[{color}]{icon} {display_name}[/{color}]"

        lines.append(line)

    # Add fix loop indicator if applicable
    if fix_attempt > 0:
        lines.append("")
        lines.append(f"[yellow]Fix Loop: Attempt {fix_attempt}/{max_attempts}[/yellow]")

    content = "\n".join(lines)
    return Panel(content, title="Pipeline Status", border_style="cyan")


def create_agent_header(agent_name: str, description: str) -> Panel:
    """Create a header panel for an agent starting execution.

    Args:
        agent_name: Name of the agent.
        description: Agent description.

    Returns:
        Rich Panel object.
    """
    return Panel(
        f"[dim]{description}[/dim]",
        title=f"[bold cyan]{agent_name}[/bold cyan]",
        border_style="cyan",
    )


def create_success_panel(message: str, title: str = "Success") -> Panel:
    """Create a success panel.

    Args:
        message: Success message.
        title: Panel title.

    Returns:
        Rich Panel object.
    """
    return Panel(
        f"[green]{message}[/green]",
        title=f"[bold green]✓ {title}[/bold green]",
        border_style="green",
    )


def create_error_panel(message: str, title: str = "Error") -> Panel:
    """Create an error panel.

    Args:
        message: Error message.
        title: Panel title.

    Returns:
        Rich Panel object.
    """
    return Panel(
        f"[red]{message}[/red]",
        title=f"[bold red]✗ {title}[/bold red]",
        border_style="red",
    )


def create_warning_panel(message: str, title: str = "Warning") -> Panel:
    """Create a warning panel.

    Args:
        message: Warning message.
        title: Panel title.

    Returns:
        Rich Panel object.
    """
    return Panel(
        f"[yellow]{message}[/yellow]",
        title=f"[bold yellow]⚠ {title}[/bold yellow]",
        border_style="yellow",
    )


def create_pipeline_summary(context: PipelineContext) -> Panel:
    """Create a summary panel for the completed pipeline.

    Args:
        context: Pipeline context with all results.

    Returns:
        Rich Panel object.
    """
    lines = []

    # Status
    if context.pipeline_completed and not context.pipeline_failed:
        lines.append("[bold green]✓ Pipeline completed successfully[/bold green]")
    elif context.pipeline_failed:
        lines.append(
            f"[bold red]✗ Pipeline failed: {context.failure_reason}[/bold red]"
        )
    else:
        lines.append("[yellow]Pipeline in progress...[/yellow]")

    lines.append("")

    # Generated files
    if context.generated_files:
        lines.append(f"[cyan]Generated Files:[/cyan] {len(context.generated_files)}")
        for filename in sorted(context.generated_files.keys())[:5]:
            lines.append(f"  • {filename}")
        if len(context.generated_files) > 5:
            lines.append(f"  ... and {len(context.generated_files) - 5} more")

    # Validation
    lines.append("")
    if context.validation_passed:
        lines.append("[green]✓ Validation passed[/green]")
    elif context.validation_errors:
        lines.append(
            f"[red]✗ Validation errors: {len(context.validation_errors)}[/red]"
        )

    # Security
    blocking = context.get_blocking_issues()
    warnings = context.get_warning_issues()
    if context.security_skipped:
        lines.append("[dim]○ Security scan skipped (run from options panel)[/dim]")
    elif context.security_passed:
        lines.append("[green]✓ Security scan passed[/green]")
    else:
        if blocking:
            lines.append(f"[red]✗ Security issues (blocking): {len(blocking)}[/red]")
        if warnings:
            lines.append(f"[yellow]⚠ Security warnings: {len(warnings)}[/yellow]")

    # Fix attempts
    if context.security_fix_attempts > 0:
        lines.append(
            f"[dim]Fix attempts: {context.security_fix_attempts}/{context.max_security_fix_attempts}[/dim]"
        )

    # Cost
    if context.cost_estimated:
        lines.append("")
        lines.append(f"[green]Monthly Cost:[/green] ${context.total_monthly_cost:,.2f}")
        lines.append(f"[green]Yearly Cost:[/green] ${context.total_yearly_cost:,.2f}")

    content = "\n".join(lines)
    border_color = (
        "green"
        if context.pipeline_completed and not context.pipeline_failed
        else "red" if context.pipeline_failed else "yellow"
    )

    return Panel(content, title="Pipeline Summary", border_style=border_color)


def print_security_issues_summary(
    console: Console,
    issues: list[SecurityIssue],
    show_table: bool = True,
) -> None:
    """Print a summary of security issues to the console.

    Args:
        console: Rich console.
        issues: List of security issues.
        show_table: Whether to show the full table.
    """
    if not issues:
        console.print("[green]No security issues found.[/green]")
        return

    blocking = [i for i in issues if i.severity.blocks_pipeline()]
    warnings = [i for i in issues if not i.severity.blocks_pipeline()]

    if show_table:
        console.print(create_security_issues_table(issues))
        console.print()

    if blocking:
        console.print(
            f"[bold red]Blocking issues (CRITICAL/HIGH): {len(blocking)}[/bold red]"
        )
    if warnings:
        console.print(f"[yellow]Warnings (MEDIUM/LOW/INFO): {len(warnings)}[/yellow]")


def print_cost_summary(
    console: Console,
    costs: list[CostBreakdown],
    total_monthly: float,
    total_yearly: float,
) -> None:
    """Print a cost summary to the console.

    Args:
        console: Rich console.
        costs: List of cost breakdowns.
        total_monthly: Total monthly cost.
        total_yearly: Total yearly cost.
    """
    if not costs:
        console.print("[yellow]No cost data available.[/yellow]")
        return

    console.print(create_cost_breakdown_table(costs, total_monthly, total_yearly))


class PipelineProgressDisplay:
    """Manages a live-updating progress display for the pipeline."""

    def __init__(self, console: Optional[Console] = None):
        """Initialize the progress display.

        Args:
            console: Rich console to use.
        """
        self.console = console or Console()
        self.agent_statuses: dict[str, AgentStatus] = {}
        self.current_agent = ""
        self.fix_attempt = 0
        self.max_attempts = 3
        self._live: Optional[Live] = None

    def start(self) -> None:
        """Start the live display."""
        self._live = Live(
            self._create_display(),
            console=self.console,
            refresh_per_second=4,
        )
        self._live.start()

    def stop(self) -> None:
        """Stop the live display."""
        if self._live:
            self._live.stop()
            self._live = None

    def update_agent_status(self, agent_name: str, status: AgentStatus) -> None:
        """Update the status of an agent.

        Args:
            agent_name: Name of the agent.
            status: New status.
        """
        self.agent_statuses[agent_name] = status
        if status == AgentStatus.RUNNING:
            self.current_agent = agent_name
        self._refresh()

    def set_fix_attempt(self, attempt: int, max_attempts: int) -> None:
        """Set the current fix attempt.

        Args:
            attempt: Current attempt number.
            max_attempts: Maximum attempts allowed.
        """
        self.fix_attempt = attempt
        self.max_attempts = max_attempts
        self._refresh()

    def _create_display(self) -> Panel:
        """Create the display panel."""
        return create_pipeline_status_panel(
            self.agent_statuses,
            self.current_agent,
            self.fix_attempt,
            self.max_attempts,
        )

    def _refresh(self) -> None:
        """Refresh the live display."""
        if self._live:
            self._live.update(self._create_display())

    def __enter__(self) -> "PipelineProgressDisplay":
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.stop()
