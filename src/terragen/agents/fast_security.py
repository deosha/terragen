"""Fast security agent using pattern-based scanning.

This agent provides instant security feedback during fix loops using
regex pattern matching. Much faster than running external tools.

The full tools (tfsec, checkov, conftest) still run for final verification.
"""

from typing import Any, Optional

from rich.console import Console

from terragen.agents.base import (
    AgentResult,
    AgentStatus,
    BaseAgent,
    IssueSeverity,
    SecurityIssue as BaseSecurityIssue,
)
from terragen.agents.context import PipelineContext
from terragen.security.pattern_scanner import PatternScanner, SecurityIssue


class FastSecurityAgent(BaseAgent):
    """Fast pattern-based security scanner for quick feedback during fix loops.

    Uses pre-built JSON rules to scan Terraform files for common security
    issues using regex pattern matching. Runs in ~50ms vs 5-10s for tfsec/checkov.

    This agent is used during fix loops for quick iteration. The full
    security agents (tfsec, checkov) run after fix loops complete.
    """

    name = "FastSecurityAgent"
    description = "Fast pattern-based security scan (~50ms)"
    is_gate = True  # Blocking issues will trigger fix

    def __init__(
        self,
        console: Optional[Console] = None,
        log_callback: Optional[Any] = None,
    ):
        """Initialize the fast security agent.

        Args:
            console: Rich console for output.
            log_callback: Callback for streaming logs to UI.
        """
        super().__init__(console, log_callback)
        self.scanner = PatternScanner()

    async def execute(self, context: PipelineContext) -> AgentResult:
        """Execute fast pattern-based security scan.

        Args:
            context: Pipeline context with generated files.

        Returns:
            AgentResult with scan results.
        """
        self._status = AgentStatus.RUNNING

        if not context.generated_files:
            self._log_warning("No files to scan")
            self._status = AgentStatus.SKIPPED
            return AgentResult(
                status=AgentStatus.SKIPPED,
                data={"reason": "No files to scan"},
            )

        # Get terraform files
        tf_files = {
            name: content
            for name, content in context.generated_files.items()
            if name.endswith(".tf")
        }

        if not tf_files:
            self._log_warning("No Terraform files to scan")
            self._status = AgentStatus.SKIPPED
            return AgentResult(
                status=AgentStatus.SKIPPED,
                data={"reason": "No Terraform files"},
            )

        self._log_info(f"Scanning {len(tf_files)} files with pattern rules...")

        # Run pattern scan
        issues = self.scanner.scan_files(tf_files, provider=context.provider)

        # Convert to base SecurityIssue format and add to context
        for issue in issues:
            base_issue = BaseSecurityIssue(
                severity=self._convert_severity(issue.severity.value),
                rule_id=issue.rule_id,
                description=f"{issue.title}: {issue.description}",
                file_path=issue.file_path,
                line_number=issue.line_number,
                resource=issue.resource_type,
                remediation=issue.remediation,
                scanner="pattern",
            )
            context.add_security_issue(base_issue)

        # Get summary
        summary = self.scanner.get_summary(issues)
        blocking_issues = self.scanner.get_blocking_issues(issues)

        if issues:
            self._log_info(
                f"Found {summary['total']} issues: "
                f"{summary['critical']} critical, {summary['high']} high, "
                f"{summary['medium']} medium"
            )

        if blocking_issues:
            self._log_warning(f"{len(blocking_issues)} blocking issue(s) found")

            # Log first few blocking issues
            for issue in blocking_issues[:3]:
                self._log_warning(
                    f"  [{issue.severity.value}] {issue.rule_id}: {issue.title} "
                    f"({issue.file_path}:{issue.line_number})"
                )

            self._status = AgentStatus.FAILED
            return AgentResult(
                status=AgentStatus.FAILED,
                data={
                    "blocking_issues": len(blocking_issues),
                    "warning_issues": summary["total"] - len(blocking_issues),
                    "issues": [i.to_dict() for i in issues],
                },
                errors=[f"{i.rule_id}: {i.title}" for i in blocking_issues[:5]],
                next_action="fix_security",
            )

        if issues:
            self._log_info(f"Found {len(issues)} non-blocking warning(s)")

        self._log_success("Pattern scan passed (no blocking issues)")
        self._status = AgentStatus.SUCCESS
        return AgentResult(
            status=AgentStatus.SUCCESS,
            data={
                "blocking_issues": 0,
                "warning_issues": len(issues),
                "issues": [i.to_dict() for i in issues],
            },
        )

    def _convert_severity(self, severity_str: str) -> IssueSeverity:
        """Convert pattern scanner severity to base IssueSeverity.

        Args:
            severity_str: Severity string from pattern scanner.

        Returns:
            IssueSeverity enum value.
        """
        mapping = {
            "CRITICAL": IssueSeverity.CRITICAL,
            "HIGH": IssueSeverity.HIGH,
            "MEDIUM": IssueSeverity.MEDIUM,
            "LOW": IssueSeverity.LOW,
            "INFO": IssueSeverity.INFO,
        }
        return mapping.get(severity_str.upper(), IssueSeverity.MEDIUM)
