"""Base classes for the multi-agent orchestration system."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from rich.console import Console

console = Console()


class AgentStatus(Enum):
    """Status of an agent execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class IssueSeverity(Enum):
    """Severity levels for security/policy issues."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"

    @classmethod
    def from_string(cls, value: str) -> "IssueSeverity":
        """Convert string to IssueSeverity, case-insensitive."""
        try:
            return cls[value.upper()]
        except KeyError:
            return cls.INFO

    def blocks_pipeline(self) -> bool:
        """Return True if this severity should block the pipeline."""
        return self in (IssueSeverity.CRITICAL, IssueSeverity.HIGH)


@dataclass
class SecurityIssue:
    """Represents a security or policy issue found during scanning."""

    severity: IssueSeverity
    rule_id: str
    description: str
    file_path: str
    line_number: int
    resource: str = ""
    remediation: str = ""
    scanner: str = ""  # "tfsec", "checkov", "conftest"

    def __str__(self) -> str:
        return f"[{self.severity.value}] {self.rule_id}: {self.description} ({self.file_path}:{self.line_number})"


@dataclass
class ValidationError:
    """Represents a Terraform validation error."""

    error_type: str  # "fmt", "init", "validate"
    message: str
    file_path: str = ""
    line_number: int = 0


@dataclass
class CostBreakdown:
    """Represents a cost estimate for a resource."""

    resource_name: str
    resource_type: str
    monthly_cost: float
    yearly_cost: float
    hourly_cost: float = 0.0
    unit: str = "USD"


@dataclass
class AgentResult:
    """Result of an agent execution."""

    status: AgentStatus
    data: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    next_action: Optional[str] = (
        None  # "fix_security", "fix_validation", "continue", None
    )

    @property
    def success(self) -> bool:
        """Return True if the agent succeeded."""
        return self.status == AgentStatus.SUCCESS

    @property
    def failed(self) -> bool:
        """Return True if the agent failed."""
        return self.status == AgentStatus.FAILED

    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.errors.append(error)


class BaseAgent(ABC):
    """Abstract base class for all pipeline agents."""

    name: str = "BaseAgent"
    description: str = "Base agent class"
    is_gate: bool = False  # If True, failure blocks the pipeline

    def __init__(
        self, console: Optional[Console] = None, log_callback: Optional[Any] = None
    ):
        """Initialize the agent with an optional Rich console and log callback."""
        self.console = console or Console()
        self._status = AgentStatus.PENDING
        self._log_callback = log_callback  # Callback to emit logs to UI

    @property
    def status(self) -> AgentStatus:
        """Get the current agent status."""
        return self._status

    @abstractmethod
    async def execute(self, context: "PipelineContext") -> AgentResult:
        """Execute the agent's task.

        Args:
            context: The shared pipeline context.

        Returns:
            AgentResult with status and any data/errors.
        """
        pass

    def _log(self, message: str, style: str = "", level: str = "info") -> None:
        """Log a message to the console and emit to callback if available."""
        prefix = f"[bold cyan][{self.name}][/bold cyan]"
        if style:
            self.console.print(f"{prefix} [{style}]{message}[/{style}]")
        else:
            self.console.print(f"{prefix} {message}")

        # Emit to callback for UI streaming
        if self._log_callback:
            from datetime import datetime

            self._log_callback(
                {
                    "log": {
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "level": level,
                        "agent": self.name,
                        "message": message,
                    }
                }
            )

    def _log_success(self, message: str) -> None:
        """Log a success message."""
        self._log(message, "green", "success")

    def _log_error(self, message: str) -> None:
        """Log an error message."""
        self._log(message, "red", "error")

    def _log_warning(self, message: str) -> None:
        """Log a warning message."""
        self._log(message, "yellow", "warning")

    def _log_info(self, message: str) -> None:
        """Log an info message."""
        self._log(message, "blue", "info")


# Import PipelineContext here to avoid circular imports
# This allows type hints to work correctly
from terragen.agents.context import PipelineContext  # noqa: E402, F401
