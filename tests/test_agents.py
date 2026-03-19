"""Tests for TerraGen multi-agent orchestration system."""

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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


class TestAgentStatus:
    """Test AgentStatus enum."""

    def test_status_values(self):
        """AgentStatus should have expected values."""
        assert AgentStatus.PENDING.value == "pending"
        assert AgentStatus.RUNNING.value == "running"
        assert AgentStatus.SUCCESS.value == "success"
        assert AgentStatus.FAILED.value == "failed"
        assert AgentStatus.SKIPPED.value == "skipped"


class TestIssueSeverity:
    """Test IssueSeverity enum."""

    def test_severity_values(self):
        """IssueSeverity should have expected values."""
        assert IssueSeverity.CRITICAL.value == "CRITICAL"
        assert IssueSeverity.HIGH.value == "HIGH"
        assert IssueSeverity.MEDIUM.value == "MEDIUM"
        assert IssueSeverity.LOW.value == "LOW"
        assert IssueSeverity.INFO.value == "INFO"

    def test_from_string(self):
        """from_string should convert case-insensitively."""
        assert IssueSeverity.from_string("critical") == IssueSeverity.CRITICAL
        assert IssueSeverity.from_string("HIGH") == IssueSeverity.HIGH
        assert IssueSeverity.from_string("Medium") == IssueSeverity.MEDIUM
        assert IssueSeverity.from_string("unknown") == IssueSeverity.INFO

    def test_blocks_pipeline(self):
        """Only CRITICAL and HIGH should block pipeline."""
        assert IssueSeverity.CRITICAL.blocks_pipeline() is True
        assert IssueSeverity.HIGH.blocks_pipeline() is True
        assert IssueSeverity.MEDIUM.blocks_pipeline() is False
        assert IssueSeverity.LOW.blocks_pipeline() is False
        assert IssueSeverity.INFO.blocks_pipeline() is False


class TestSecurityIssue:
    """Test SecurityIssue dataclass."""

    def test_str_representation(self):
        """SecurityIssue should have readable string representation."""
        issue = SecurityIssue(
            severity=IssueSeverity.HIGH,
            rule_id="AWS001",
            description="S3 bucket is public",
            file_path="main.tf",
            line_number=42,
            scanner="tfsec",
        )
        result = str(issue)
        assert "HIGH" in result
        assert "AWS001" in result
        assert "main.tf:42" in result


class TestAgentResult:
    """Test AgentResult dataclass."""

    def test_success_property(self):
        """success should return True for SUCCESS status."""
        result = AgentResult(status=AgentStatus.SUCCESS)
        assert result.success is True
        assert result.failed is False

    def test_failed_property(self):
        """failed should return True for FAILED status."""
        result = AgentResult(status=AgentStatus.FAILED)
        assert result.success is False
        assert result.failed is True

    def test_add_error(self):
        """add_error should append to errors list."""
        result = AgentResult(status=AgentStatus.FAILED)
        result.add_error("Error 1")
        result.add_error("Error 2")
        assert len(result.errors) == 2
        assert "Error 1" in result.errors


class TestPipelineContext:
    """Test PipelineContext dataclass."""

    def test_default_values(self):
        """PipelineContext should have sensible defaults."""
        context = PipelineContext(user_prompt="Create an S3 bucket")
        assert context.provider == "aws"
        assert context.region == "us-east-1"
        assert context.max_security_fix_attempts == 3
        assert context.security_fix_attempts == 0
        assert context.pipeline_started is False
        assert context.pipeline_completed is False

    def test_get_blocking_issues(self):
        """get_blocking_issues should filter by severity."""
        context = PipelineContext(user_prompt="test")
        context.security_issues = [
            SecurityIssue(
                severity=IssueSeverity.CRITICAL,
                rule_id="C1",
                description="Critical issue",
                file_path="main.tf",
                line_number=1,
            ),
            SecurityIssue(
                severity=IssueSeverity.HIGH,
                rule_id="H1",
                description="High issue",
                file_path="main.tf",
                line_number=2,
            ),
            SecurityIssue(
                severity=IssueSeverity.MEDIUM,
                rule_id="M1",
                description="Medium issue",
                file_path="main.tf",
                line_number=3,
            ),
        ]

        blocking = context.get_blocking_issues()
        assert len(blocking) == 2
        assert all(
            i.severity in [IssueSeverity.CRITICAL, IssueSeverity.HIGH] for i in blocking
        )

    def test_get_warning_issues(self):
        """get_warning_issues should return non-blocking issues."""
        context = PipelineContext(user_prompt="test")
        context.security_issues = [
            SecurityIssue(
                severity=IssueSeverity.CRITICAL,
                rule_id="C1",
                description="Critical",
                file_path="main.tf",
                line_number=1,
            ),
            SecurityIssue(
                severity=IssueSeverity.LOW,
                rule_id="L1",
                description="Low",
                file_path="main.tf",
                line_number=2,
            ),
        ]

        warnings = context.get_warning_issues()
        assert len(warnings) == 1
        assert warnings[0].severity == IssueSeverity.LOW

    def test_can_attempt_fix(self):
        """can_attempt_fix should respect max attempts."""
        context = PipelineContext(user_prompt="test")
        context.max_security_fix_attempts = 3

        assert context.can_attempt_fix() is True

        context.security_fix_attempts = 3
        assert context.can_attempt_fix() is False

    def test_increment_fix_attempts(self):
        """increment_fix_attempts should increment counter."""
        context = PipelineContext(user_prompt="test")
        assert context.security_fix_attempts == 0

        context.increment_fix_attempts()
        assert context.security_fix_attempts == 1

    def test_mark_failed(self):
        """mark_failed should update state."""
        context = PipelineContext(user_prompt="test")
        context.mark_failed("Test failure")

        assert context.pipeline_failed is True
        assert context.failure_reason == "Test failure"

    def test_mark_completed(self):
        """mark_completed should update state."""
        context = PipelineContext(user_prompt="test")
        context.mark_completed()

        assert context.pipeline_completed is True
        assert context.pipeline_failed is False

    def test_clear_security_issues(self):
        """clear_security_issues should reset issues."""
        context = PipelineContext(user_prompt="test")
        context.security_issues = [
            SecurityIssue(
                severity=IssueSeverity.HIGH,
                rule_id="H1",
                description="Issue",
                file_path="main.tf",
                line_number=1,
            )
        ]
        context.security_passed = True

        context.clear_security_issues()

        assert len(context.security_issues) == 0
        assert context.security_passed is False

    def test_to_dict(self):
        """to_dict should serialize context."""
        context = PipelineContext(
            user_prompt="Create S3",
            provider="aws",
            region="us-east-1",
        )
        context.validation_passed = True

        result = context.to_dict()

        assert result["user_prompt"] == "Create S3"
        assert result["provider"] == "aws"
        assert result["validation_passed"] is True

    def test_update_generated_files(self):
        """update_generated_files should read files from disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Create test files
            (output_dir / "main.tf").write_text("resource aws_s3_bucket {}")
            (output_dir / "variables.tf").write_text("variable name {}")

            context = PipelineContext(
                user_prompt="test",
                output_dir=output_dir,
            )
            context.update_generated_files()

            assert "main.tf" in context.generated_files
            assert "variables.tf" in context.generated_files
            assert "aws_s3_bucket" in context.generated_files["main.tf"]


class TestCostBreakdown:
    """Test CostBreakdown dataclass."""

    def test_default_values(self):
        """CostBreakdown should have correct defaults."""
        cost = CostBreakdown(
            resource_name="web-server",
            resource_type="EC2",
            monthly_cost=45.0,
            yearly_cost=540.0,
        )
        assert cost.hourly_cost == 0.0
        assert cost.unit == "USD"


class TestValidationError:
    """Test ValidationError dataclass."""

    def test_fields(self):
        """ValidationError should store all fields."""
        error = ValidationError(
            error_type="validate",
            message="Invalid resource reference",
            file_path="main.tf",
            line_number=10,
        )
        assert error.error_type == "validate"
        assert error.message == "Invalid resource reference"
        assert error.file_path == "main.tf"
        assert error.line_number == 10


class TestVisualization:
    """Test visualization functions."""

    def test_create_security_issues_table(self):
        """create_security_issues_table should create Rich table."""
        from terragen.agents.visualization import create_security_issues_table

        issues = [
            SecurityIssue(
                severity=IssueSeverity.CRITICAL,
                rule_id="AWS001",
                description="S3 bucket public",
                file_path="main.tf",
                line_number=42,
                scanner="tfsec",
            ),
        ]

        table = create_security_issues_table(issues)
        assert table is not None
        assert table.title == "Security Issues"

    def test_create_cost_breakdown_table(self):
        """create_cost_breakdown_table should create Rich table."""
        from terragen.agents.visualization import create_cost_breakdown_table

        costs = [
            CostBreakdown(
                resource_name="web-server",
                resource_type="EC2",
                monthly_cost=45.0,
                yearly_cost=540.0,
            ),
        ]

        table = create_cost_breakdown_table(costs, 45.0, 540.0)
        assert table is not None
        assert table.title == "Infrastructure Cost Estimate"


class TestValidationAgent:
    """Test ValidationAgent."""

    @pytest.mark.asyncio
    async def test_validation_agent_no_tf_files(self):
        """ValidationAgent should fail if no .tf files exist."""
        from terragen.agents.validation import ValidationAgent

        with tempfile.TemporaryDirectory() as tmpdir:
            context = PipelineContext(
                user_prompt="test",
                output_dir=Path(tmpdir),
            )

            agent = ValidationAgent()
            result = await agent.execute(context)

            assert result.status == AgentStatus.FAILED
            assert any("No Terraform files" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_validation_agent_nonexistent_dir(self):
        """ValidationAgent should fail for nonexistent directory."""
        from terragen.agents.validation import ValidationAgent

        context = PipelineContext(
            user_prompt="test",
            output_dir=Path("/nonexistent/directory"),
        )

        agent = ValidationAgent()
        result = await agent.execute(context)

        assert result.status == AgentStatus.FAILED


class TestSecurityAgent:
    """Test SecurityAgent."""

    @pytest.mark.asyncio
    async def test_security_agent_nonexistent_dir(self):
        """SecurityAgent should fail for nonexistent directory."""
        from terragen.agents.security import SecurityAgent

        context = PipelineContext(
            user_prompt="test",
            output_dir=Path("/nonexistent/directory"),
        )

        agent = SecurityAgent()
        result = await agent.execute(context)

        assert result.status == AgentStatus.FAILED


class TestCheckovAgent:
    """Test CheckovAgent."""

    @pytest.mark.asyncio
    async def test_checkov_agent_nonexistent_dir(self):
        """CheckovAgent should fail for nonexistent directory."""
        from terragen.agents.checkov import CheckovAgent

        context = PipelineContext(
            user_prompt="test",
            output_dir=Path("/nonexistent/directory"),
        )

        agent = CheckovAgent()
        result = await agent.execute(context)

        assert result.status == AgentStatus.FAILED


class TestPolicyAgent:
    """Test PolicyAgent."""

    @pytest.mark.asyncio
    async def test_policy_agent_nonexistent_dir(self):
        """PolicyAgent should fail for nonexistent directory."""
        from terragen.agents.policy import PolicyAgent

        context = PipelineContext(
            user_prompt="test",
            output_dir=Path("/nonexistent/directory"),
        )

        agent = PolicyAgent()
        result = await agent.execute(context)

        assert result.status == AgentStatus.FAILED


class TestCostEstimationAgent:
    """Test CostEstimationAgent."""

    @pytest.mark.asyncio
    async def test_cost_agent_nonexistent_dir(self):
        """CostEstimationAgent should fail for nonexistent directory."""
        from terragen.agents.cost import CostEstimationAgent

        context = PipelineContext(
            user_prompt="test",
            output_dir=Path("/nonexistent/directory"),
        )

        agent = CostEstimationAgent()
        result = await agent.execute(context)

        assert result.status == AgentStatus.FAILED


class TestClarificationAgent:
    """Test ClarificationAgent."""

    @pytest.mark.asyncio
    async def test_clarification_skip(self):
        """ClarificationAgent should skip when requested."""
        from terragen.agents.clarification import ClarificationAgent

        context = PipelineContext(
            user_prompt="test",
            skip_clarify=True,
        )

        agent = ClarificationAgent()
        result = await agent.execute(context)

        assert result.status == AgentStatus.SKIPPED
        assert context.clarification_skipped is True


class TestOrchestratorIntegration:
    """Integration tests for PipelineOrchestrator."""

    def test_orchestrator_initialization(self):
        """PipelineOrchestrator should initialize with all agents."""
        from terragen.agents.orchestrator import PipelineOrchestrator

        orchestrator = PipelineOrchestrator()

        assert orchestrator.clarification_agent is not None
        assert orchestrator.code_gen_agent is not None
        assert orchestrator.validation_agent is not None
        assert orchestrator.security_agent is not None
        assert orchestrator.checkov_agent is not None
        assert orchestrator.policy_agent is not None
        assert orchestrator.cost_agent is not None

    def test_run_pipeline_function(self):
        """run_pipeline convenience function should create context."""
        from terragen.agents.orchestrator import run_pipeline

        # Just test that it's importable and has correct signature
        import inspect

        sig = inspect.signature(run_pipeline)
        params = list(sig.parameters.keys())

        assert "prompt" in params
        assert "output_dir" in params
        assert "provider" in params
        assert "skip_clarify" in params
        assert "skip_cost" in params
        assert "max_security_fixes" in params
