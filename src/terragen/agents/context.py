"""Pipeline context for sharing state between agents."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from terragen.agents.base import (
    CostBreakdown,
    SecurityIssue,
    ValidationError,
    IssueSeverity,
)


@dataclass
class PipelineContext:
    """Shared state passed through the agent pipeline.

    This context is created at the start of the pipeline and modified
    by each agent as they execute. It carries all information needed
    for code generation, validation, security scanning, and cost estimation.
    """

    # Input configuration
    user_prompt: str
    provider: str = "aws"
    region: str = "us-east-1"
    output_dir: Path = field(default_factory=lambda: Path("./output"))

    # Pipeline configuration
    skip_clarify: bool = False
    skip_cost: bool = False
    skip_security: bool = (
        False  # Skip automatic security scanning (user can run manually)
    )
    max_security_fix_attempts: int = 3
    chat_mode: bool = False
    backend_config: Optional[dict[str, Any]] = None
    learn_from: Optional[Path] = None

    # Clarification results
    clarifications: dict[str, Any] = field(default_factory=dict)
    clarification_skipped: bool = False

    # Generated code
    generated_files: dict[str, str] = field(default_factory=dict)  # filename -> content

    # Validation state
    validation_passed: bool = False
    validation_errors: list[ValidationError] = field(default_factory=list)

    # Security state (merged from all scanners)
    security_issues: list[SecurityIssue] = field(default_factory=list)
    security_passed: bool = False
    security_skipped: bool = False  # True if security scans were skipped
    security_fix_attempts: int = 0

    # Cost estimation
    cost_breakdown: list[CostBreakdown] = field(default_factory=list)
    total_monthly_cost: float = 0.0
    total_yearly_cost: float = 0.0
    cost_estimated: bool = False

    # Pipeline metadata
    current_agent: str = ""
    pipeline_started: bool = False
    pipeline_completed: bool = False
    pipeline_failed: bool = False
    failure_reason: str = ""

    def get_blocking_issues(self) -> list[SecurityIssue]:
        """Return security issues that block the pipeline (CRITICAL + HIGH)."""
        return [
            issue for issue in self.security_issues if issue.severity.blocks_pipeline()
        ]

    def get_warning_issues(self) -> list[SecurityIssue]:
        """Return security issues that are warnings (MEDIUM, LOW, INFO)."""
        return [
            issue
            for issue in self.security_issues
            if not issue.severity.blocks_pipeline()
        ]

    def has_blocking_issues(self) -> bool:
        """Return True if there are any blocking security issues."""
        return len(self.get_blocking_issues()) > 0

    def has_validation_errors(self) -> bool:
        """Return True if there are any validation errors."""
        return len(self.validation_errors) > 0

    def has_fixable_issues(self) -> bool:
        """Return True if there are any issues that need fixing (validation or security)."""
        return self.has_blocking_issues() or self.has_validation_errors()

    def can_attempt_fix(self) -> bool:
        """Return True if we can attempt another security fix."""
        return self.security_fix_attempts < self.max_security_fix_attempts

    def increment_fix_attempts(self) -> None:
        """Increment the fix attempt counter."""
        self.security_fix_attempts += 1

    def add_security_issue(self, issue: SecurityIssue) -> None:
        """Add a security issue to the context."""
        self.security_issues.append(issue)

    def clear_security_issues(self) -> None:
        """Clear all security issues (before re-scanning)."""
        self.security_issues.clear()
        self.security_passed = False

    def add_validation_error(self, error: ValidationError) -> None:
        """Add a validation error to the context."""
        self.validation_errors.append(error)

    def clear_validation_errors(self) -> None:
        """Clear all validation errors (before re-validating)."""
        self.validation_errors.clear()
        self.validation_passed = False

    def mark_failed(self, reason: str) -> None:
        """Mark the pipeline as failed."""
        self.pipeline_failed = True
        self.failure_reason = reason

    def mark_completed(self) -> None:
        """Mark the pipeline as successfully completed."""
        self.pipeline_completed = True
        self.pipeline_failed = False

    def get_generated_file_paths(self) -> list[Path]:
        """Return list of paths for all generated files."""
        return [self.output_dir / filename for filename in self.generated_files.keys()]

    def get_terraform_files(self) -> dict[str, str]:
        """Return only .tf files from generated files."""
        return {
            name: content
            for name, content in self.generated_files.items()
            if name.endswith(".tf")
        }

    def update_generated_files(self) -> None:
        """Read current state of generated files from disk."""
        self.generated_files.clear()
        if self.output_dir.exists():
            # Read all relevant file types
            file_patterns = ["*.tf", "*.tfvars", "*.md", "*.json", "*.yaml", "*.yml"]
            for pattern in file_patterns:
                for file_path in self.output_dir.glob(pattern):
                    try:
                        self.generated_files[file_path.name] = file_path.read_text()
                    except Exception:
                        pass
            # Also read .github workflow files
            workflow_dir = self.output_dir / ".github" / "workflows"
            if workflow_dir.exists():
                for workflow_file in workflow_dir.glob("*.yml"):
                    rel_path = f".github/workflows/{workflow_file.name}"
                    try:
                        self.generated_files[rel_path] = workflow_file.read_text()
                    except Exception:
                        pass

    def get_issues_summary(self) -> str:
        """Return a summary of all issues (validation + security) for the LLM to fix."""
        lines = []

        # Add validation errors first (they're usually more critical)
        if self.validation_errors:
            lines.append("## Validation Errors to Fix:\n")
            for i, error in enumerate(self.validation_errors, 1):
                location = (
                    f"{error.file_path}:{error.line_number}"
                    if error.file_path
                    else "unknown"
                )
                lines.append(
                    f"{i}. [{error.error_type}] {error.message}\n"
                    f"   Location: {location}\n"
                )
            lines.append("")

        # Add security issues
        blocking_issues = self.get_blocking_issues()
        if blocking_issues:
            lines.append("## Security Issues to Fix:\n")
            for i, issue in enumerate(blocking_issues, 1):
                lines.append(
                    f"{i}. [{issue.severity.value}] {issue.rule_id}: {issue.description}\n"
                    f"   File: {issue.file_path}:{issue.line_number}\n"
                    f"   Resource: {issue.resource}\n"
                )
                if issue.remediation:
                    lines.append(f"   Remediation: {issue.remediation}\n")
                lines.append("")

        if not lines:
            return "No issues found."

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert context to a dictionary for serialization."""
        return {
            "user_prompt": self.user_prompt,
            "provider": self.provider,
            "region": self.region,
            "output_dir": str(self.output_dir),
            "clarifications": self.clarifications,
            "validation_passed": self.validation_passed,
            "validation_errors": [
                {
                    "error_type": e.error_type,
                    "message": e.message,
                    "file_path": e.file_path,
                    "line_number": e.line_number,
                }
                for e in self.validation_errors
            ],
            "security_passed": self.security_passed,
            "security_skipped": self.security_skipped,
            "security_issues": [
                {
                    "severity": i.severity.value,
                    "rule_id": i.rule_id,
                    "description": i.description,
                    "file_path": i.file_path,
                    "line_number": i.line_number,
                    "resource": i.resource,
                    "remediation": i.remediation,
                    "scanner": i.scanner,
                }
                for i in self.security_issues
            ],
            "security_fix_attempts": self.security_fix_attempts,
            "cost_breakdown": [
                {
                    "resource_name": c.resource_name,
                    "resource_type": c.resource_type,
                    "monthly_cost": c.monthly_cost,
                    "yearly_cost": c.yearly_cost,
                    "hourly_cost": c.hourly_cost,
                }
                for c in self.cost_breakdown
            ],
            "total_monthly_cost": self.total_monthly_cost,
            "total_yearly_cost": self.total_yearly_cost,
            "pipeline_completed": self.pipeline_completed,
            "pipeline_failed": self.pipeline_failed,
            "failure_reason": self.failure_reason,
        }
