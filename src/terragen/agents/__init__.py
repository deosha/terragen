"""Multi-agent orchestration system for TerraGen.

This package provides a pipeline of specialized agents for:
- Clarification: Auto-detect if questions needed, ask smart questions
- Code Generation: Generate Terraform code, fix issues
- Validation: Run terraform fmt/init/validate
- Security: Run tfsec security scans
- Checkov: Run Checkov policy scans
- Policy: Custom policy compliance (OPA/Conftest)
- Cost Estimation: Display cost visualization
"""

from terragen.agents.base import (
    AgentResult,
    AgentStatus,
    BaseAgent,
    CostBreakdown,
    IssueSeverity,
    SecurityIssue,
    ValidationError,
)
from terragen.agents.context import PipelineContext

__all__ = [
    # Base classes
    "AgentResult",
    "AgentStatus",
    "BaseAgent",
    "CostBreakdown",
    "IssueSeverity",
    "PipelineContext",
    "SecurityIssue",
    "ValidationError",
    # Agents (imported lazily to avoid circular imports)
    "ClarificationAgent",
    "CheckovAgent",
    "CodeGenerationAgent",
    "CostEstimationAgent",
    "PipelineOrchestrator",
    "PolicyAgent",
    "SecurityAgent",
    "ValidationAgent",
]


def __getattr__(name: str):
    """Lazy import of agents to avoid circular imports."""
    if name == "ClarificationAgent":
        from terragen.agents.clarification import ClarificationAgent
        return ClarificationAgent
    elif name == "CheckovAgent":
        from terragen.agents.checkov import CheckovAgent
        return CheckovAgent
    elif name == "CodeGenerationAgent":
        from terragen.agents.code_generation import CodeGenerationAgent
        return CodeGenerationAgent
    elif name == "CostEstimationAgent":
        from terragen.agents.cost import CostEstimationAgent
        return CostEstimationAgent
    elif name == "PipelineOrchestrator":
        from terragen.agents.orchestrator import PipelineOrchestrator
        return PipelineOrchestrator
    elif name == "PolicyAgent":
        from terragen.agents.policy import PolicyAgent
        return PolicyAgent
    elif name == "SecurityAgent":
        from terragen.agents.security import SecurityAgent
        return SecurityAgent
    elif name == "ValidationAgent":
        from terragen.agents.validation import ValidationAgent
        return ValidationAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
