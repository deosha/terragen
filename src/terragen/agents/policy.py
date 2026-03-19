"""Policy agent for running OPA/Conftest custom policy checks."""

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


# Default policy directory relative to the project root
DEFAULT_POLICY_DIR = Path(__file__).parent.parent.parent.parent / "policies"


class PolicyAgent(BaseAgent):
    """Agent that runs custom OPA/Conftest policy checks.

    Uses Conftest to run Rego policies against Terraform code
    for custom compliance and security requirements.
    """

    name = "PolicyAgent"
    description = "Runs custom OPA/Conftest policies on Terraform code"
    is_gate = True  # Policy issues can block pipeline

    def __init__(
        self,
        console: Optional[Console] = None,
        policy_dir: Optional[Path] = None,
        log_callback: Optional[Any] = None,
    ):
        """Initialize the Policy agent.

        Args:
            console: Rich console for output.
            policy_dir: Directory containing Rego policy files.
            log_callback: Callback for streaming logs to UI.
        """
        super().__init__(console, log_callback)
        self.policy_dir = policy_dir or DEFAULT_POLICY_DIR
        self.timeout = 60  # seconds

    async def execute(self, context: PipelineContext) -> AgentResult:
        """Execute custom policy checks.

        Args:
            context: Pipeline context with output directory.

        Returns:
            AgentResult with policy check results.
        """
        self._status = AgentStatus.RUNNING

        output_dir = context.output_dir
        if not output_dir.exists():
            self._log_error(f"Output directory does not exist: {output_dir}")
            return AgentResult(
                status=AgentStatus.FAILED,
                errors=["Output directory does not exist"],
            )

        # Check if conftest is installed
        if not await self._check_conftest_installed():
            self._log_warning("conftest not installed, skipping custom policy checks")
            self._status = AgentStatus.SKIPPED
            return AgentResult(
                status=AgentStatus.SKIPPED,
                data={"reason": "conftest not installed"},
            )

        # Check if policy directory exists and has policies
        if not self.policy_dir.exists():
            self._log_warning(f"Policy directory not found: {self.policy_dir}")
            self._status = AgentStatus.SKIPPED
            return AgentResult(
                status=AgentStatus.SKIPPED,
                data={"reason": "No policy directory found"},
            )

        policy_files = list(self.policy_dir.glob("*.rego"))
        if not policy_files:
            self._log_warning("No .rego policy files found")
            self._status = AgentStatus.SKIPPED
            return AgentResult(
                status=AgentStatus.SKIPPED,
                data={"reason": "No policy files found"},
            )

        self._log_info(f"Running custom policy checks ({len(policy_files)} policies)...")
        issues = await self._run_conftest(output_dir)

        # Add issues to context
        for issue in issues:
            context.add_security_issue(issue)

        # Determine if we pass based on blocking issues
        blocking_issues = [i for i in issues if i.severity.blocks_pipeline()]
        warning_issues = [i for i in issues if not i.severity.blocks_pipeline()]

        if issues:
            print_security_issues_summary(self.console, issues, show_table=True)

        if blocking_issues:
            self._log_error(f"Found {len(blocking_issues)} blocking policy violation(s)")
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

        self._log_success("Custom policy checks passed")
        self._status = AgentStatus.SUCCESS
        return AgentResult(
            status=AgentStatus.SUCCESS,
            data={
                "blocking_issues": 0,
                "warning_issues": len(warning_issues),
                "issues": [self._issue_to_dict(i) for i in warning_issues],
            },
        )

    async def _check_conftest_installed(self) -> bool:
        """Check if conftest is installed.

        Returns:
            True if conftest is available.
        """
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["conftest", "--version"],
                    capture_output=True,
                    timeout=10,
                ),
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    async def _run_conftest(self, output_dir: Path) -> list[SecurityIssue]:
        """Run conftest and parse results.

        Args:
            output_dir: Directory containing Terraform files.

        Returns:
            List of security issues found.
        """
        issues = []

        # Get all .tf files
        tf_files = list(output_dir.glob("*.tf"))
        if not tf_files:
            return issues

        try:
            # Build conftest command
            cmd = [
                "conftest", "test",
                "--policy", str(self.policy_dir),
                "--output", "json",
                "--all-namespaces",
            ] + [str(f) for f in tf_files]

            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    cwd=output_dir,
                ),
            )

            # conftest returns non-zero if there are failures, but we still parse output
            if result.stdout:
                try:
                    data = json.loads(result.stdout)
                    issues = self._parse_conftest_output(data)
                except json.JSONDecodeError:
                    self._log_warning("Failed to parse conftest JSON output")

        except subprocess.TimeoutExpired:
            self._log_error("conftest scan timed out")
        except FileNotFoundError:
            self._log_warning("conftest not found")
        except Exception as e:
            self._log_error(f"Error running conftest: {str(e)}")

        return issues

    def _parse_conftest_output(self, data: list[dict[str, Any]]) -> list[SecurityIssue]:
        """Parse conftest JSON output into SecurityIssue objects.

        Args:
            data: Parsed JSON output from conftest.

        Returns:
            List of SecurityIssue objects.
        """
        issues = []

        for file_result in data:
            filename = file_result.get("filename", "")
            if filename:
                filename = Path(filename).name

            # Process failures (deny rules)
            for failure in file_result.get("failures", []):
                issue = self._create_issue_from_result(
                    failure,
                    filename,
                    severity=IssueSeverity.HIGH,  # deny = HIGH by default
                )
                issues.append(issue)

            # Process warnings (warn rules)
            for warning in file_result.get("warnings", []):
                issue = self._create_issue_from_result(
                    warning,
                    filename,
                    severity=IssueSeverity.MEDIUM,  # warn = MEDIUM
                )
                issues.append(issue)

        return issues

    def _create_issue_from_result(
        self,
        result: dict[str, Any],
        filename: str,
        severity: IssueSeverity,
    ) -> SecurityIssue:
        """Create a SecurityIssue from a conftest result.

        Args:
            result: Single conftest result.
            filename: Source file name.
            severity: Issue severity.

        Returns:
            SecurityIssue object.
        """
        msg = result.get("msg", "Policy violation")

        # Try to extract rule ID from metadata or message
        metadata = result.get("metadata", {})
        rule_id = metadata.get("rule_id", "")
        if not rule_id:
            # Try to extract from namespace
            namespace = file_result.get("namespace", "") if "file_result" in dir() else ""
            rule_id = f"POLICY_{namespace.upper()}" if namespace else "POLICY_CUSTOM"

        # Check for severity override in metadata
        if "severity" in metadata:
            severity = IssueSeverity.from_string(metadata["severity"])

        return SecurityIssue(
            severity=severity,
            rule_id=rule_id,
            description=msg,
            file_path=filename,
            line_number=0,  # conftest doesn't provide line numbers
            resource=metadata.get("resource", ""),
            remediation=metadata.get("remediation", ""),
            scanner="conftest",
        )

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
