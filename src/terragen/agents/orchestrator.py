"""Pipeline orchestrator for multi-agent workflow."""

from typing import Optional, Callable, Any
from datetime import datetime

from rich.console import Console
from rich.panel import Panel

from terragen.agents.base import AgentResult, AgentStatus, BaseAgent
from terragen.agents.context import PipelineContext
from terragen.agents.visualization import (
    PipelineProgressDisplay,
    create_pipeline_summary,
    create_success_panel,
    create_error_panel,
    create_warning_panel,
)

# Import agents
from terragen.agents.clarification import ClarificationAgent
from terragen.agents.code_generation import CodeGenerationAgent
from terragen.agents.validation import ValidationAgent
from terragen.agents.security import SecurityAgent
from terragen.agents.checkov import CheckovAgent
from terragen.agents.policy import PolicyAgent
from terragen.agents.cost import CostEstimationAgent
from terragen.agents.fast_security import FastSecurityAgent


# Type for session update callback
SessionUpdateCallback = Callable[[dict[str, Any]], None]


class PipelineOrchestrator:
    """Orchestrates the multi-agent pipeline for Terraform generation.

    Pipeline flow:
    1. ClarificationAgent - Auto-detect if questions needed
    2. CodeGenerationAgent - Generate Terraform code
    3. ValidationAgent - Run terraform fmt/init/validate
    4. SecurityAgent - Run tfsec security scans
    5. CheckovAgent - Run Checkov policy scans
    6. PolicyAgent - Run custom OPA/Conftest policies
    7. If security issues found:
       a. CodeGenerationAgent (fix mode) - Fix issues
       b. Re-run steps 3-6
       c. Repeat up to max_security_fix_attempts
    8. CostEstimationAgent - Display cost visualization
    """

    def __init__(
        self,
        console: Optional[Console] = None,
        show_progress: bool = True,
        session_callback: Optional[SessionUpdateCallback] = None,
    ):
        """Initialize the orchestrator.

        Args:
            console: Rich console for output.
            show_progress: Whether to show live progress display.
            session_callback: Callback to update session state (for web UI).
        """
        self.console = console or Console()
        self.show_progress = show_progress
        self.session_callback = session_callback

        # Create event callback wrapper for agents
        def agent_event_callback(updates: dict):
            if self.session_callback:
                self.session_callback(updates)

        # Initialize agents with log callback for UI streaming
        log_cb = agent_event_callback if session_callback else None
        self.clarification_agent = ClarificationAgent(
            console=self.console, log_callback=log_cb
        )
        self.code_gen_agent = CodeGenerationAgent(
            console=self.console,
            event_callback=agent_event_callback if session_callback else None,
        )
        self.validation_agent = ValidationAgent(
            console=self.console, log_callback=log_cb
        )
        self.fast_security_agent = FastSecurityAgent(
            console=self.console, log_callback=log_cb
        )
        self.security_agent = SecurityAgent(console=self.console, log_callback=log_cb)
        self.checkov_agent = CheckovAgent(console=self.console, log_callback=log_cb)
        self.policy_agent = PolicyAgent(console=self.console, log_callback=log_cb)
        self.cost_agent = CostEstimationAgent(console=self.console, log_callback=log_cb)

        # Track agent statuses
        self.agent_statuses: dict[str, AgentStatus] = {
            "ClarificationAgent": AgentStatus.PENDING,
            "CodeGenerationAgent": AgentStatus.PENDING,
            "ValidationAgent": AgentStatus.PENDING,
            "FastSecurityAgent": AgentStatus.PENDING,
            "SecurityAgent": AgentStatus.PENDING,
            "CheckovAgent": AgentStatus.PENDING,
            "PolicyAgent": AgentStatus.PENDING,
            "CostEstimationAgent": AgentStatus.PENDING,
        }

    async def run(self, context: PipelineContext) -> PipelineContext:
        """Run the complete pipeline.

        Args:
            context: Pipeline context with initial configuration.

        Returns:
            Updated context with results.
        """
        context.pipeline_started = True

        self.console.print(
            Panel.fit(
                "[bold blue]TerraGen Multi-Agent Pipeline[/bold blue]\n"
                "[dim]Generating production-ready Terraform with security gates[/dim]",
                border_style="blue",
            )
        )

        try:
            # Step 1: Clarification
            result = await self._run_agent(
                self.clarification_agent,
                context,
                "Clarification",
            )
            if result.failed and self.clarification_agent.is_gate:
                context.mark_failed("Clarification failed")
                return context

            # Step 2: Code Generation
            result = await self._run_agent(
                self.code_gen_agent,
                context,
                "Code Generation",
            )
            if result.failed:
                context.mark_failed("Code generation failed")
                return context

            # Step 3-6: Validation and Security
            if context.skip_security:
                # Run validation only, skip security scanners
                context.clear_validation_errors()
                result = await self._run_agent(
                    self.validation_agent,
                    context,
                    "Validation",
                )
                if result.failed:
                    context.mark_failed("Validation failed")
                    return context

                # Skip security scanning - user can run manually from options panel
                self._emit_log(
                    "Skipping security scanning (run manually from options)",
                    level="info",
                )
                self.agent_statuses["SecurityAgent"] = AgentStatus.SKIPPED
                self.agent_statuses["CheckovAgent"] = AgentStatus.SKIPPED
                self.agent_statuses["PolicyAgent"] = AgentStatus.SKIPPED
                context.security_skipped = True  # Mark as skipped, not passed
            else:
                # Run full security loop (includes validation)
                passed = await self._run_security_loop(context)
                if not passed:
                    return context

            # Step 7: Cost Estimation
            if not context.skip_cost:
                await self._run_agent(
                    self.cost_agent,
                    context,
                    "Cost Estimation",
                )
            else:
                self.agent_statuses["CostEstimationAgent"] = AgentStatus.SKIPPED
                self.console.print("[dim]Skipping cost estimation (--skip-cost)[/dim]")

            # Pipeline complete
            context.mark_completed()

            # Emit completion logs for UI
            self._emit_log("Pipeline completed successfully", level="success")
            self._emit_log(
                f"Generated {len(context.generated_files)} files",
                level="info",
                details=", ".join(sorted(context.generated_files.keys())[:5]),
            )
            if context.cost_estimated:
                self._emit_log(
                    f"Estimated cost: ${context.total_monthly_cost:.2f}/month",
                    level="info",
                )
            else:
                self._emit_log("Cost estimation skipped or unavailable", level="info")

            # Show summary
            self.console.print()
            self.console.print(create_pipeline_summary(context))

            if context.pipeline_failed:
                return context

            # Show success panel with next steps
            self._show_success_message(context)

        except KeyboardInterrupt:
            context.mark_failed("Pipeline cancelled by user")
            self.console.print(create_warning_panel("Pipeline cancelled by user"))
        except Exception as e:
            context.mark_failed(str(e))
            self.console.print(create_error_panel(f"Pipeline failed: {e}"))

        return context

    def _emit_log(
        self,
        message: str,
        level: str = "info",
        agent: Optional[str] = None,
        details: Optional[str] = None,
    ) -> None:
        """Emit a log entry to the session callback.

        Args:
            message: Log message.
            level: Log level (info, success, warning, error).
            agent: Agent name (optional).
            details: Additional details (optional).
        """
        if self.session_callback:
            log_entry = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "level": level,
                "message": message,
            }
            if agent:
                log_entry["agent"] = agent
            if details:
                log_entry["details"] = details
            self.session_callback({"log": log_entry})

    def _update_session(self, updates: dict[str, Any]) -> None:
        """Update session state via callback.

        Args:
            updates: Dictionary of session fields to update.
        """
        if self.session_callback:
            self.session_callback(updates)

    async def _run_agent(
        self,
        agent: BaseAgent,
        context: PipelineContext,
        phase_name: str,
    ) -> AgentResult:
        """Run a single agent and update tracking.

        Args:
            agent: Agent to run.
            context: Pipeline context.
            phase_name: Human-readable phase name.

        Returns:
            AgentResult from the agent.
        """
        self.console.print(f"\n[bold cyan]>>> {phase_name}[/bold cyan]")
        self.console.print(f"[dim]{agent.description}[/dim]\n")

        context.current_agent = agent.name
        self.agent_statuses[agent.name] = AgentStatus.RUNNING

        # Emit log and update session
        self._emit_log(f"Running {phase_name}...", level="info", agent=agent.name)
        self._update_session({"current_agent": agent.name})

        result = await agent.execute(context)

        self.agent_statuses[agent.name] = result.status

        if result.status == AgentStatus.SUCCESS:
            self.console.print(f"[green]<<< {phase_name} complete[/green]")
            self._emit_log(f"{phase_name} complete", level="success", agent=agent.name)
            self._update_session({"completed_agent": agent.name})
        elif result.status == AgentStatus.SKIPPED:
            self.console.print(f"[dim]<<< {phase_name} skipped[/dim]")
            self._emit_log(f"{phase_name} skipped", level="info", agent=agent.name)
            self._update_session({"skipped_agent": agent.name})
        elif result.status == AgentStatus.FAILED:
            self.console.print(f"[red]<<< {phase_name} failed[/red]")
            error_details = "; ".join(result.errors[:3]) if result.errors else None
            self._emit_log(
                f"{phase_name} failed",
                level="error",
                agent=agent.name,
                details=error_details,
            )
            self._update_session({"failed_agent": agent.name})
            for error in result.errors[:3]:  # Show first 3 errors
                self.console.print(f"[red]    {error}[/red]")

        # Emit security issues if this was a security scan
        if agent.name in ("SecurityAgent", "CheckovAgent", "PolicyAgent"):
            self._emit_security_issues(result, agent.name)

        return result

    def _emit_security_issues(self, result: AgentResult, agent_name: str) -> None:
        """Emit security issues found by a security agent.

        Args:
            result: AgentResult from security agent.
            agent_name: Name of the security agent.
        """
        if not result.data:
            return

        issues = result.data.get("issues", [])
        blocking = result.data.get("blocking_issues", 0)
        warnings = result.data.get("warning_issues", 0)

        if blocking > 0:
            self._emit_log(
                f"Found {blocking} blocking issues, {warnings} warnings",
                level="warning",
                agent=agent_name,
            )
            # Emit individual blocking issues
            for issue in issues[:5]:  # Limit to first 5
                severity = issue.get("severity", "UNKNOWN")
                if severity in ("CRITICAL", "HIGH"):
                    desc = issue.get("description", "Unknown issue")[:60]
                    file_path = issue.get("file_path", "")
                    line = issue.get("line_number", 0)
                    self._emit_log(
                        f"[{severity}] {desc}",
                        level="error",
                        details=f"{file_path}:{line}" if file_path else None,
                    )
        elif warnings > 0:
            self._emit_log(
                f"Found {warnings} warnings (non-blocking)",
                level="info",
                agent=agent_name,
            )

    async def _run_security_loop(self, context: PipelineContext) -> bool:
        """Run the validation and security check loop with fixes.

        Args:
            context: Pipeline context.

        Returns:
            True if all checks pass, False otherwise.
        """
        # Initial validation (must pass before security scans)
        context.clear_validation_errors()
        result = await self._run_agent(
            self.validation_agent,
            context,
            "Validation",
        )
        if result.failed:
            # Initial validation failed - try to fix
            if context.can_attempt_fix():
                attempt = context.security_fix_attempts + 1
                max_attempts = context.max_security_fix_attempts
                self.console.print(
                    f"[yellow]Attempting to fix validation issues "
                    f"(attempt {attempt}/{max_attempts})[/yellow]"
                )
                context.increment_fix_attempts()
                self._emit_log(
                    f"Attempting to fix validation issues (attempt {attempt}/{max_attempts})",
                    level="warning",
                )
                self._update_session(
                    {
                        "fix_attempt": attempt,
                        "max_fix_attempts": max_attempts,
                    }
                )

                fix_result = await self.code_gen_agent.execute_fix(context)
                if fix_result.failed:
                    context.mark_failed("Could not fix validation issues")
                    return False

                # Re-run validation after fix
                context.clear_validation_errors()
                context.update_generated_files()
                result = await self._run_agent(
                    self.validation_agent,
                    context,
                    "Validation (retry)",
                )
                if result.failed:
                    context.mark_failed("Validation still failing after fix attempt")
                    return False
            else:
                context.mark_failed("Validation failed")
                return False

        # Security scan loop (validation already passed at this point)
        # Strategy:
        # 1. Initial scan with FULL tools (tfsec, checkov, opa) - accurate detection
        # 2. Fix loops use FAST pattern scanner - quick iteration (~50ms vs 10s)
        # 3. After fix loops complete, run FULL tools for final verification

        # --- Initial full scan ---
        self._emit_log(
            "Running full security scan (tfsec, checkov, opa)...", level="info"
        )
        context.clear_security_issues()

        # Run security scans (tfsec)
        await self._run_agent(
            self.security_agent,
            context,
            "Security (tfsec)",
        )

        # Run Checkov
        await self._run_agent(
            self.checkov_agent,
            context,
            "Checkov",
        )

        # Run policy checks
        await self._run_agent(
            self.policy_agent,
            context,
            "Policy (OPA)",
        )

        # --- Fix loop with fast pattern scanner ---
        while context.has_blocking_issues() and context.can_attempt_fix():
            # Save current file state before security fixes
            saved_files = dict(context.generated_files)
            blocking_count = len(context.get_blocking_issues())

            attempt = context.security_fix_attempts + 1
            max_attempts = context.max_security_fix_attempts
            self.console.print(
                f"\n[yellow]Found {blocking_count} blocking security issue(s). "
                f"Attempting fix (attempt {attempt}/{max_attempts})[/yellow]"
            )
            context.increment_fix_attempts()

            self._emit_log(
                f"Found {blocking_count} blocking security issues. Attempting fix (attempt {attempt}/{max_attempts})",
                level="warning",
            )
            self._update_session(
                {
                    "fix_attempt": attempt,
                    "max_fix_attempts": max_attempts,
                }
            )

            # Try to fix security issues
            fix_result = await self.code_gen_agent.execute_fix(context)
            if fix_result.failed:
                context.mark_failed("Could not fix security issues")
                return False

            # Update files from disk after fix
            context.update_generated_files()

            # Quick validation to catch regressions
            context.clear_validation_errors()
            self._emit_log("Validating security fix...", level="info")
            validation_result = await self._run_agent(
                self.validation_agent,
                context,
                "Validation (post-fix)",
            )

            if validation_result.failed:
                # Security fix broke validation - rollback!
                self.console.print(
                    "[red]Security fix broke validation - rolling back[/red]"
                )
                self._emit_log(
                    "Security fix broke validation - rolling back to previous state",
                    level="error",
                )

                # Restore saved files
                context.generated_files = saved_files
                for filename, content in saved_files.items():
                    file_path = context.output_dir / filename
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_text(content)

                # This counts as a failed fix attempt
                if not context.can_attempt_fix():
                    context.mark_failed(
                        f"Security fixes keep breaking validation after {context.security_fix_attempts} attempts"
                    )
                    return False
                # Continue loop to try again
                continue

            # Validation passed - run FAST pattern scan for quick feedback
            context.clear_security_issues()
            self._emit_log("Running fast pattern scan...", level="info")
            await self._run_agent(
                self.fast_security_agent,
                context,
                "Fast Security Scan",
            )

        # --- Final verification with full tools ---
        if context.security_fix_attempts > 0:
            # We made fixes, re-run full tools for final verification
            self._emit_log(
                "Running final security verification (tfsec, checkov, opa)...",
                level="info",
            )
            context.clear_security_issues()

            await self._run_agent(
                self.security_agent,
                context,
                "Security (tfsec) - Final",
            )

            await self._run_agent(
                self.checkov_agent,
                context,
                "Checkov - Final",
            )

            await self._run_agent(
                self.policy_agent,
                context,
                "Policy (OPA) - Final",
            )

        # Check final result
        if context.has_blocking_issues():
            # Security issues remain but we've exhausted fix attempts
            # Don't fail - continue with warnings so code is still usable
            context.security_passed = False
            self._emit_log(
                f"Security issues remain after {context.security_fix_attempts} fix attempts. "
                "Code generated with warnings - review security issues before deploying.",
                level="warning",
            )
            return True  # Continue pipeline with warnings
        else:
            # All checks passed
            context.security_passed = True
            self._emit_log("All security checks passed", level="success")
            return True

    def _show_success_message(self, context: PipelineContext) -> None:
        """Show success message with next steps.

        Args:
            context: Pipeline context.
        """
        files = list(context.generated_files.keys())
        tf_files = [f for f in files if f.endswith(".tf")]

        message_parts = [
            f"Generated {len(files)} files in {context.output_dir}",
            "",
            "[bold]Generated Terraform files:[/bold]",
        ]
        for tf_file in sorted(tf_files)[:10]:
            message_parts.append(f"  - {tf_file}")
        if len(tf_files) > 10:
            message_parts.append(f"  ... and {len(tf_files) - 10} more")

        if context.cost_estimated:
            message_parts.extend(
                [
                    "",
                    f"[bold]Estimated Cost:[/bold]",
                    f"  Monthly: ${context.total_monthly_cost:,.2f}",
                    f"  Yearly:  ${context.total_yearly_cost:,.2f}",
                ]
            )

        message_parts.extend(
            [
                "",
                "[bold]Next Steps:[/bold]",
                f"  cd {context.output_dir}",
                "  terraform init",
                "  terraform plan",
                "  terraform apply",
            ]
        )

        self.console.print(
            create_success_panel(
                "\n".join(message_parts),
                title="Generation Complete",
            )
        )


async def run_pipeline(
    prompt: str,
    output_dir: str,
    provider: str = "aws",
    region: str = "us-east-1",
    skip_clarify: bool = False,
    skip_cost: bool = False,
    max_security_fixes: int = 3,
    chat_mode: bool = False,
    backend_config: Optional[dict] = None,
    learn_from: Optional[str] = None,
) -> PipelineContext:
    """Convenience function to run the full pipeline.

    Args:
        prompt: User's infrastructure request.
        output_dir: Directory to write generated files.
        provider: Cloud provider (aws, gcp, azure).
        region: Cloud region.
        skip_clarify: Skip clarification questions.
        skip_cost: Skip cost estimation.
        max_security_fixes: Maximum security fix attempts.
        chat_mode: Enable interactive chat mode.
        backend_config: Backend configuration dict.
        learn_from: Path to existing repo for pattern learning.

    Returns:
        PipelineContext with results.
    """
    from pathlib import Path

    context = PipelineContext(
        user_prompt=prompt,
        provider=provider,
        region=region,
        output_dir=Path(output_dir),
        skip_clarify=skip_clarify,
        skip_cost=skip_cost,
        max_security_fix_attempts=max_security_fixes,
        chat_mode=chat_mode,
        backend_config=backend_config,
        learn_from=Path(learn_from) if learn_from else None,
    )

    orchestrator = PipelineOrchestrator()
    return await orchestrator.run(context)
