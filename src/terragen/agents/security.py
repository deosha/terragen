"""Security agent for running tfsec security scans."""

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any, Optional

from rich.console import Console

from terragen.agents.base import (
    AgentResult,
    AgentStatus,
    BaseAgent,
    IssueSeverity,
    SecurityIssue,
)
from terragen.agents.context import PipelineContext
from terragen.agents.visualization import print_security_issues_summary


class SecurityAgent(BaseAgent):
    """Agent that runs tfsec security scans.

    Scans Terraform code for security misconfigurations and
    reports issues with severity levels.
    """

    name = "SecurityAgent"
    description = "Runs tfsec security scans on Terraform code"
    is_gate = True  # Security issues can block pipeline

    def __init__(self, console: Optional[Console] = None, log_callback: Optional[Any] = None):
        """Initialize the security agent."""
        super().__init__(console, log_callback)
        self.timeout = 120  # seconds

    async def execute(self, context: PipelineContext) -> AgentResult:
        """Execute tfsec security scan.

        Args:
            context: Pipeline context with output directory.

        Returns:
            AgentResult with security scan results.
        """
        self._status = AgentStatus.RUNNING

        output_dir = context.output_dir
        if not output_dir.exists():
            self._log_error(f"Output directory does not exist: {output_dir}")
            return AgentResult(
                status=AgentStatus.FAILED,
                errors=["Output directory does not exist"],
            )

        # Check if tfsec is installed
        if not await self._check_tfsec_installed():
            self._log_warning("tfsec not installed, skipping security scan")
            self._status = AgentStatus.SKIPPED
            return AgentResult(
                status=AgentStatus.SKIPPED,
                data={"reason": "tfsec not installed"},
            )

        self._log_info("Running tfsec security scan...")
        issues = await self._run_tfsec(output_dir)

        # Add issues to context (don't clear - other scanners may have added issues)
        for issue in issues:
            context.add_security_issue(issue)

        # Determine if we pass based on blocking issues
        blocking_issues = [i for i in issues if i.severity.blocks_pipeline()]
        warning_issues = [i for i in issues if not i.severity.blocks_pipeline()]

        if issues:
            print_security_issues_summary(self.console, issues)
            # Log issues to stream for UI
            self._log_info(f"┌{'─' * 90}┐")
            self._log_info(f"│ {'Severity':<10} │ {'Rule ID':<15} │ {'File:Line':<20} │ {'Description':<35} │")
            self._log_info(f"├{'─' * 90}┤")
            for issue in issues[:10]:  # Limit to 10 for terminal
                sev = issue.severity.value
                rule = (issue.rule_id or "")[:14]
                file_line = f"{Path(issue.file_path).name if issue.file_path else '-'}:{issue.line_number or '-'}"[:19]
                desc = (issue.description or "")[:34]
                self._log_info(f"│ {sev:<10} │ {rule:<15} │ {file_line:<20} │ {desc:<35} │")
            if len(issues) > 10:
                self._log_info(f"│ ... and {len(issues) - 10} more issues {'─' * 56} │")
            self._log_info(f"└{'─' * 90}┘")

        if blocking_issues:
            self._log_error(f"Found {len(blocking_issues)} blocking security issue(s)")
            self._status = AgentStatus.FAILED
            return AgentResult(
                status=AgentStatus.FAILED,
                data={
                    "blocking_issues": len(blocking_issues),
                    "warning_issues": len(warning_issues),
                    "issues": [self._issue_to_dict(i) for i in issues],
                },
                errors=[str(i) for i in blocking_issues],
                next_action="fix_security",
            )

        if warning_issues:
            self._log_warning(f"Found {len(warning_issues)} warning(s) (non-blocking)")

        self._log_success("Security scan passed (no blocking issues)")
        self._status = AgentStatus.SUCCESS
        context.security_passed = True
        return AgentResult(
            status=AgentStatus.SUCCESS,
            data={
                "blocking_issues": 0,
                "warning_issues": len(warning_issues),
                "issues": [self._issue_to_dict(i) for i in warning_issues],
            },
        )

    async def _check_tfsec_installed(self) -> bool:
        """Check if tfsec is installed.

        Returns:
            True if tfsec is available.
        """
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["tfsec", "--version"],
                    capture_output=True,
                    timeout=10,
                ),
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    async def _run_tfsec(self, output_dir: Path) -> list[SecurityIssue]:
        """Run tfsec and parse results.

        Args:
            output_dir: Directory containing Terraform files.

        Returns:
            List of security issues found.
        """
        issues = []
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    [
                        "tfsec",
                        str(output_dir),
                        "--format", "json",
                        "--soft-fail",  # Don't return non-zero exit code
                    ],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                ),
            )

            if result.stdout:
                try:
                    data = json.loads(result.stdout)
                    issues = self._parse_tfsec_output(data)
                except json.JSONDecodeError:
                    self._log_warning("Failed to parse tfsec JSON output")

        except subprocess.TimeoutExpired:
            self._log_error("tfsec scan timed out")
        except FileNotFoundError:
            self._log_warning("tfsec not found")
        except Exception as e:
            self._log_error(f"Error running tfsec: {str(e)}")

        return issues

    def _parse_tfsec_output(self, data: dict[str, Any]) -> list[SecurityIssue]:
        """Parse tfsec JSON output into SecurityIssue objects.

        Args:
            data: Parsed JSON output from tfsec.

        Returns:
            List of SecurityIssue objects.
        """
        issues = []
        results = data.get("results", [])

        for result in results:
            severity_str = result.get("severity", "INFO")
            severity = IssueSeverity.from_string(severity_str)

            # Extract location
            location = result.get("location", {})
            filename = location.get("filename", "")
            start_line = location.get("start_line", 0)

            # Make filename relative if it's absolute
            if filename.startswith(str(self.timeout)):
                filename = Path(filename).name

            issue = SecurityIssue(
                severity=severity,
                rule_id=result.get("rule_id", result.get("long_id", "UNKNOWN")),
                description=result.get("description", result.get("rule_description", "Unknown issue")),
                file_path=filename,
                line_number=start_line,
                resource=result.get("resource", ""),
                remediation=result.get("resolution", result.get("impact", "")),
                scanner="tfsec",
            )
            issues.append(issue)

        return issues

    def _issue_to_dict(self, issue: SecurityIssue) -> dict[str, Any]:
        """Convert SecurityIssue to dictionary.

        Args:
            issue: SecurityIssue to convert.

        Returns:
            Dictionary representation.
        """
        return {
            "severity": issue.severity.value,
            "rule_id": issue.rule_id,
            "description": issue.description,
            "file_path": issue.file_path,
            "line_number": issue.line_number,
            "resource": issue.resource,
            "remediation": issue.remediation,
            "scanner": issue.scanner,
        }
