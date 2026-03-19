"""Checkov agent for running policy scans."""

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


class CheckovAgent(BaseAgent):
    """Agent that runs Checkov policy scans.

    Scans Terraform code for security and compliance issues
    using Checkov's built-in policies.
    """

    name = "CheckovAgent"
    description = "Runs Checkov policy scans on Terraform code"
    is_gate = True  # Policy issues can block pipeline

    def __init__(self, console: Optional[Console] = None, log_callback: Optional[Any] = None):
        """Initialize the Checkov agent."""
        super().__init__(console, log_callback)
        self.timeout = 180  # seconds (Checkov can be slow)

    async def execute(self, context: PipelineContext) -> AgentResult:
        """Execute Checkov policy scan.

        Args:
            context: Pipeline context with output directory.

        Returns:
            AgentResult with policy scan results.
        """
        self._status = AgentStatus.RUNNING

        output_dir = context.output_dir
        if not output_dir.exists():
            self._log_error(f"Output directory does not exist: {output_dir}")
            return AgentResult(
                status=AgentStatus.FAILED,
                errors=["Output directory does not exist"],
            )

        # Check if checkov is installed
        if not await self._check_checkov_installed():
            self._log_warning("checkov not installed, skipping policy scan")
            self._status = AgentStatus.SKIPPED
            return AgentResult(
                status=AgentStatus.SKIPPED,
                data={"reason": "checkov not installed"},
            )

        self._log_info("Running Checkov policy scan...")
        issues = await self._run_checkov(output_dir)

        # Add issues to context
        for issue in issues:
            context.add_security_issue(issue)

        # Determine if we pass based on blocking issues
        blocking_issues = [i for i in issues if i.severity.blocks_pipeline()]
        warning_issues = [i for i in issues if not i.severity.blocks_pipeline()]

        if issues:
            print_security_issues_summary(self.console, issues, show_table=True)

        if blocking_issues:
            self._log_error(f"Found {len(blocking_issues)} blocking policy issue(s)")
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
            self._log_warning(f"Found {len(warning_issues)} policy warning(s) (non-blocking)")

        self._log_success("Checkov scan passed (no blocking issues)")
        self._status = AgentStatus.SUCCESS
        return AgentResult(
            status=AgentStatus.SUCCESS,
            data={
                "blocking_issues": 0,
                "warning_issues": len(warning_issues),
                "issues": [self._issue_to_dict(i) for i in warning_issues],
            },
        )

    async def _check_checkov_installed(self) -> bool:
        """Check if checkov is installed.

        Returns:
            True if checkov is available.
        """
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["checkov", "--version"],
                    capture_output=True,
                    timeout=10,
                ),
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    async def _run_checkov(self, output_dir: Path) -> list[SecurityIssue]:
        """Run checkov and parse results.

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
                        "checkov",
                        "-d", str(output_dir),
                        "--framework", "terraform",
                        "--output", "json",
                        "--soft-fail",  # Don't return non-zero exit code
                        "--quiet",  # Reduce output
                    ],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                ),
            )

            if result.stdout:
                try:
                    # Checkov may output multiple JSON objects, take the first
                    data = json.loads(result.stdout)
                    issues = self._parse_checkov_output(data)
                except json.JSONDecodeError:
                    # Try parsing line by line
                    for line in result.stdout.strip().split("\n"):
                        if line.strip().startswith("{"):
                            try:
                                data = json.loads(line)
                                issues.extend(self._parse_checkov_output(data))
                                break
                            except json.JSONDecodeError:
                                continue
                    if not issues:
                        self._log_warning("Failed to parse checkov JSON output")

        except subprocess.TimeoutExpired:
            self._log_error("checkov scan timed out")
        except FileNotFoundError:
            self._log_warning("checkov not found")
        except Exception as e:
            self._log_error(f"Error running checkov: {str(e)}")

        return issues

    def _parse_checkov_output(self, data: dict[str, Any]) -> list[SecurityIssue]:
        """Parse checkov JSON output into SecurityIssue objects.

        Args:
            data: Parsed JSON output from checkov.

        Returns:
            List of SecurityIssue objects.
        """
        issues = []

        # Handle different checkov output formats
        results = data.get("results", {})

        # Process failed checks
        failed_checks = results.get("failed_checks", [])
        for check in failed_checks:
            severity = self._map_checkov_severity(check.get("check_id", ""))

            # Extract file info
            file_path = check.get("file_path", "")
            if file_path.startswith("/"):
                file_path = Path(file_path).name

            file_line = check.get("file_line_range", [0, 0])
            line_number = file_line[0] if file_line else 0

            issue = SecurityIssue(
                severity=severity,
                rule_id=check.get("check_id", "UNKNOWN"),
                description=check.get("check_name", "Unknown policy check"),
                file_path=file_path,
                line_number=line_number,
                resource=check.get("resource", ""),
                remediation=check.get("guideline", ""),
                scanner="checkov",
            )
            issues.append(issue)

        return issues

    def _map_checkov_severity(self, check_id: str) -> IssueSeverity:
        """Map checkov check ID to severity.

        Checkov doesn't provide severity directly, so we map based on check patterns.
        CKV_AWS_* checks are generally categorized by their nature.

        Args:
            check_id: Checkov check ID (e.g., CKV_AWS_1).

        Returns:
            IssueSeverity level.
        """
        # Critical checks - encryption, public access
        critical_patterns = [
            "CKV_AWS_19",  # S3 public access
            "CKV_AWS_20",  # S3 public ACL
            "CKV_AWS_21",  # S3 versioning (data loss)
            "CKV_AWS_57",  # S3 public read
            "CKV_AWS_18",  # S3 access logging
            "CKV_AWS_145",  # S3 encryption
        ]

        # High severity - security groups, IAM
        high_patterns = [
            "CKV_AWS_23",  # Security group ingress 0.0.0.0
            "CKV_AWS_24",  # Security group SSH from internet
            "CKV_AWS_25",  # Security group RDP from internet
            "CKV_AWS_40",  # IAM password policy
            "CKV_AWS_49",  # IAM policy attached to user
            "CKV_AWS_1",   # IAM password policy strength
        ]

        # Medium severity - logging, tagging
        medium_patterns = [
            "CKV_AWS_50",  # X-ray tracing
            "CKV_AWS_45",  # Lambda in VPC
        ]

        if any(check_id.startswith(p.rstrip("*")) for p in critical_patterns):
            return IssueSeverity.CRITICAL
        elif any(check_id.startswith(p.rstrip("*")) for p in high_patterns):
            return IssueSeverity.HIGH
        elif any(check_id.startswith(p.rstrip("*")) for p in medium_patterns):
            return IssueSeverity.MEDIUM
        else:
            # Default to MEDIUM for unknown checks
            return IssueSeverity.MEDIUM

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
