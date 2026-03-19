"""Fast pattern-based security scanner using pre-built rules.

This scanner provides instant security feedback during fix loops by using
regex pattern matching instead of running external tools like tfsec/checkov.

The full tools (tfsec, checkov, conftest) still run for final verification
after pattern-based fixes are complete.
"""

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class Severity(Enum):
    """Security issue severity levels."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"

    def blocks_pipeline(self) -> bool:
        """Return True if this severity should block the pipeline."""
        return self in (Severity.CRITICAL, Severity.HIGH)

    @classmethod
    def from_string(cls, value: str) -> "Severity":
        """Create Severity from string value."""
        try:
            return cls(value.upper())
        except ValueError:
            return cls.MEDIUM


@dataclass
class SecurityIssue:
    """A security issue found during scanning."""
    rule_id: str
    severity: Severity
    title: str
    description: str
    file_path: str
    line_number: int
    resource_type: str
    remediation: str
    scanner: str = "pattern"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "resource_type": self.resource_type,
            "remediation": self.remediation,
            "scanner": self.scanner,
        }


class PatternScanner:
    """Fast pattern-based security scanner.

    Uses pre-built JSON rules to scan Terraform files for common security
    issues using regex pattern matching. Much faster than running external
    tools, ideal for quick feedback during fix loops.

    Example:
        scanner = PatternScanner()
        issues = scanner.scan_files({"main.tf": content}, provider="aws")
    """

    RULES_DIR = Path(__file__).parent / "rules"

    def __init__(self):
        """Initialize the pattern scanner with rules from JSON files."""
        self._rules_cache: dict[str, list[dict]] = {}

    def _load_rules(self, provider: str) -> list[dict]:
        """Load rules for a specific provider.

        Args:
            provider: Cloud provider (aws, gcp, azure).

        Returns:
            List of rule dictionaries.
        """
        if provider in self._rules_cache:
            return self._rules_cache[provider]

        rules_file = self.RULES_DIR / f"{provider}.json"
        if not rules_file.exists():
            return []

        try:
            data = json.loads(rules_file.read_text())
            rules = data.get("rules", [])
            self._rules_cache[provider] = rules
            return rules
        except (json.JSONDecodeError, IOError):
            return []

    def _detect_provider(self, files: dict[str, str]) -> str:
        """Auto-detect cloud provider from Terraform files.

        Args:
            files: Dictionary of filename to content.

        Returns:
            Detected provider (aws, gcp, azure) or 'aws' as default.
        """
        all_content = "\n".join(files.values())

        # Check for provider blocks
        if 'provider "aws"' in all_content or "aws_" in all_content:
            return "aws"
        if 'provider "google"' in all_content or "google_" in all_content:
            return "gcp"
        if 'provider "azurerm"' in all_content or "azurerm_" in all_content:
            return "azure"

        return "aws"  # Default

    def _find_line_number(self, content: str, match_start: int) -> int:
        """Find the line number for a match position.

        Args:
            content: Full file content.
            match_start: Character position of match.

        Returns:
            1-indexed line number.
        """
        return content[:match_start].count("\n") + 1

    def _check_anti_patterns(self, content: str, anti_patterns: list[str]) -> bool:
        """Check if any anti-pattern exists in the content.

        Anti-patterns are patterns that indicate the issue has been addressed.
        If any anti-pattern matches, the issue is not reported.

        Args:
            content: File content to check.
            anti_patterns: List of regex patterns.

        Returns:
            True if any anti-pattern matches (issue is fixed).
        """
        for pattern in anti_patterns:
            try:
                if re.search(pattern, content, re.IGNORECASE | re.DOTALL):
                    return True
            except re.error:
                continue
        return False

    def _find_resource_context(
        self,
        content: str,
        match: re.Match,
        resource_type: str,
    ) -> tuple[str, int]:
        """Find the resource block containing a match.

        For rules that check for missing configurations, we need to find
        the resource block and report the issue at its start.

        Args:
            content: File content.
            match: Regex match object.
            resource_type: Type of resource to find.

        Returns:
            Tuple of (resource_name, line_number).
        """
        # For resource-level checks, find the enclosing resource block
        resource_pattern = rf'resource\s+"{resource_type}"\s+"([^"]+)"'

        # Search backwards from match position for resource declaration
        before_match = content[:match.start()]
        resource_matches = list(re.finditer(resource_pattern, before_match))

        if resource_matches:
            last_resource = resource_matches[-1]
            resource_name = last_resource.group(1)
            line_num = self._find_line_number(content, last_resource.start())
            return resource_name, line_num

        # If no resource found before, search from beginning
        first_match = re.search(resource_pattern, content)
        if first_match:
            return first_match.group(1), self._find_line_number(content, first_match.start())

        return "unknown", self._find_line_number(content, match.start())

    def scan_file(
        self,
        filename: str,
        content: str,
        provider: str,
    ) -> list[SecurityIssue]:
        """Scan a single file for security issues.

        Args:
            filename: Name of the file.
            content: File content.
            provider: Cloud provider.

        Returns:
            List of security issues found.
        """
        if not filename.endswith(".tf"):
            return []

        issues: list[SecurityIssue] = []
        rules = self._load_rules(provider)

        for rule in rules:
            rule_id = rule.get("id", "UNKNOWN")
            severity = Severity.from_string(rule.get("severity", "MEDIUM"))
            title = rule.get("title", "Security issue")
            description = rule.get("description", "")
            resource_type = rule.get("resource_type", "any")
            pattern = rule.get("pattern", "")
            anti_patterns = rule.get("anti_patterns", [])
            remediation = rule.get("remediation", "")

            if not pattern:
                continue

            try:
                # First check if any anti-pattern matches (issue already fixed)
                if anti_patterns and self._check_anti_patterns(content, anti_patterns):
                    continue

                # Find all matches of the vulnerability pattern
                for match in re.finditer(pattern, content, re.IGNORECASE | re.DOTALL):
                    # For resource-level rules, find the resource context
                    if resource_type != "any" and match.group(0).startswith("resource"):
                        resource_name = match.group(1) if match.lastindex else "unknown"
                        line_num = self._find_line_number(content, match.start())
                    else:
                        resource_name, line_num = self._find_resource_context(
                            content, match, resource_type
                        )

                    issues.append(SecurityIssue(
                        rule_id=rule_id,
                        severity=severity,
                        title=title,
                        description=description,
                        file_path=filename,
                        line_number=line_num,
                        resource_type=f"{resource_type}.{resource_name}",
                        remediation=remediation,
                        scanner="pattern",
                    ))

                    # Only report once per rule per file for resource-level rules
                    if rule.get("resource_type") != "any":
                        break

            except re.error:
                continue

        return issues

    def scan_files(
        self,
        files: dict[str, str],
        provider: Optional[str] = None,
    ) -> list[SecurityIssue]:
        """Scan multiple files for security issues.

        Args:
            files: Dictionary of filename to content.
            provider: Cloud provider (auto-detected if not specified).

        Returns:
            List of all security issues found.
        """
        if not provider:
            provider = self._detect_provider(files)

        all_issues: list[SecurityIssue] = []

        for filename, content in files.items():
            issues = self.scan_file(filename, content, provider)
            all_issues.extend(issues)

        # Deduplicate issues (same rule + file + line)
        seen = set()
        unique_issues = []
        for issue in all_issues:
            key = (issue.rule_id, issue.file_path, issue.line_number)
            if key not in seen:
                seen.add(key)
                unique_issues.append(issue)

        # Sort by severity (critical first), then by file, then by line
        severity_order = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
            Severity.INFO: 4,
        }
        unique_issues.sort(
            key=lambda i: (severity_order[i.severity], i.file_path, i.line_number)
        )

        return unique_issues

    def scan_directory(
        self,
        directory: Path,
        provider: Optional[str] = None,
    ) -> list[SecurityIssue]:
        """Scan a directory of Terraform files.

        Args:
            directory: Path to directory containing .tf files.
            provider: Cloud provider (auto-detected if not specified).

        Returns:
            List of all security issues found.
        """
        files = {}
        for tf_file in directory.glob("*.tf"):
            try:
                files[tf_file.name] = tf_file.read_text()
            except IOError:
                continue

        return self.scan_files(files, provider)

    def get_blocking_issues(self, issues: list[SecurityIssue]) -> list[SecurityIssue]:
        """Filter issues to only those that should block the pipeline.

        Args:
            issues: List of all issues.

        Returns:
            List of blocking issues (CRITICAL and HIGH severity).
        """
        return [i for i in issues if i.severity.blocks_pipeline()]

    def get_summary(self, issues: list[SecurityIssue]) -> dict:
        """Get a summary of issues by severity.

        Args:
            issues: List of issues.

        Returns:
            Dictionary with counts by severity.
        """
        summary = {
            "total": len(issues),
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "blocking": 0,
        }

        for issue in issues:
            severity_key = issue.severity.value.lower()
            if severity_key in summary:
                summary[severity_key] += 1
            if issue.severity.blocks_pipeline():
                summary["blocking"] += 1

        return summary
