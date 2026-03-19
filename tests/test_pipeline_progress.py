"""Tests for pipeline progress, SSE streaming, and security fix loop."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import datetime

from terragen.agents.base import AgentResult, AgentStatus, SecurityIssue, IssueSeverity
from terragen.agents.context import PipelineContext
from terragen.agents.orchestrator import PipelineOrchestrator


class TestEventCallback:
    """Test event callback system for UI streaming."""

    def test_orchestrator_accepts_callback(self):
        """Orchestrator should accept session_callback parameter."""
        callback = MagicMock()
        orchestrator = PipelineOrchestrator(session_callback=callback)
        assert orchestrator.session_callback == callback

    def test_emit_log_calls_callback(self):
        """_emit_log should call session_callback with log entry."""
        callback = MagicMock()
        orchestrator = PipelineOrchestrator(session_callback=callback)

        orchestrator._emit_log("Test message", level="info", agent="TestAgent")

        callback.assert_called_once()
        call_args = callback.call_args[0][0]
        assert "log" in call_args
        assert call_args["log"]["message"] == "Test message"
        assert call_args["log"]["level"] == "info"
        assert "timestamp" in call_args["log"]

    def test_emit_log_without_callback(self):
        """_emit_log should not fail without callback."""
        orchestrator = PipelineOrchestrator(session_callback=None)
        # Should not raise
        orchestrator._emit_log("Test message", level="info")

    def test_update_session_calls_callback(self):
        """_update_session should call session_callback with updates."""
        callback = MagicMock()
        orchestrator = PipelineOrchestrator(session_callback=callback)

        orchestrator._update_session({"current_agent": "TestAgent", "fix_attempt": 1})

        callback.assert_called_once_with(
            {
                "current_agent": "TestAgent",
                "fix_attempt": 1,
            }
        )

    def test_emit_security_issues(self):
        """_emit_security_issues should log blocking issues."""
        callback = MagicMock()
        orchestrator = PipelineOrchestrator(session_callback=callback)

        result = AgentResult(
            status=AgentStatus.FAILED,
            data={
                "blocking_issues": 2,
                "warning_issues": 1,
                "issues": [
                    {
                        "severity": "CRITICAL",
                        "description": "S3 bucket is public",
                        "file_path": "main.tf",
                        "line_number": 42,
                    },
                    {
                        "severity": "HIGH",
                        "description": "No encryption",
                        "file_path": "main.tf",
                        "line_number": 50,
                    },
                ],
            },
        )

        orchestrator._emit_security_issues(result, "SecurityAgent")

        # Should have multiple calls: summary + individual issues
        assert callback.call_count >= 2


class TestSecurityFixLoopRollback:
    """Test security fix loop with rollback on validation failure."""

    @pytest.fixture
    def temp_context(self):
        """Create a temporary context for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            # Create initial valid terraform files
            (output_dir / "main.tf").write_text(
                'resource "aws_s3_bucket" "test" {\n  bucket = "test"\n}'
            )
            (output_dir / "variables.tf").write_text(
                'variable "name" {\n  default = "test"\n}'
            )

            context = PipelineContext(
                user_prompt="Create S3 bucket",
                output_dir=output_dir,
                max_security_fix_attempts=3,
            )
            context.update_generated_files()
            yield context

    @pytest.mark.asyncio
    async def test_files_saved_before_security_fix(self, temp_context):
        """Files should be saved before attempting security fix."""
        orchestrator = PipelineOrchestrator(show_progress=False)

        # Track if files were saved
        saved_files = None

        original_execute = orchestrator.code_gen_agent.execute_fix

        async def mock_execute_fix(context):
            nonlocal saved_files
            # At this point, files should have been saved
            saved_files = dict(context.generated_files)
            return AgentResult(status=AgentStatus.SUCCESS)

        orchestrator.code_gen_agent.execute_fix = mock_execute_fix

        # Mock validation to pass initially
        orchestrator.validation_agent.execute = AsyncMock(
            return_value=AgentResult(status=AgentStatus.SUCCESS)
        )

        # Mock security to find issues first time, pass second time
        call_count = [0]

        async def mock_security(context):
            call_count[0] += 1
            if call_count[0] == 1:
                context.add_security_issue(
                    SecurityIssue(
                        severity=IssueSeverity.CRITICAL,
                        rule_id="TEST001",
                        description="Test issue",
                        file_path="main.tf",
                        line_number=1,
                    )
                )
                return AgentResult(
                    status=AgentStatus.FAILED,
                    data={"blocking_issues": 1, "warning_issues": 0, "issues": []},
                )
            return AgentResult(status=AgentStatus.SUCCESS)

        orchestrator.security_agent.execute = mock_security
        orchestrator.checkov_agent.execute = AsyncMock(
            return_value=AgentResult(status=AgentStatus.SUCCESS)
        )
        orchestrator.policy_agent.execute = AsyncMock(
            return_value=AgentResult(status=AgentStatus.SUCCESS)
        )

        await orchestrator._run_security_loop(temp_context)

        # Files should have been saved
        assert saved_files is not None
        assert "main.tf" in saved_files

    @pytest.mark.asyncio
    async def test_rollback_on_validation_failure_after_fix(self, temp_context):
        """Should rollback files if security fix breaks validation."""
        orchestrator = PipelineOrchestrator(show_progress=False)

        original_content = temp_context.generated_files["main.tf"]

        # Mock initial validation to pass
        validation_calls = [0]

        async def mock_validation(context):
            validation_calls[0] += 1
            if validation_calls[0] == 1:
                # Initial validation passes
                return AgentResult(status=AgentStatus.SUCCESS)
            else:
                # Post-fix validation fails
                return AgentResult(
                    status=AgentStatus.FAILED,
                    errors=["Validation failed after fix"],
                )

        orchestrator.validation_agent.execute = mock_validation

        # Mock security to always find issues (to trigger fix loop)
        async def mock_security(context):
            context.add_security_issue(
                SecurityIssue(
                    severity=IssueSeverity.CRITICAL,
                    rule_id="TEST001",
                    description="Test issue",
                    file_path="main.tf",
                    line_number=1,
                )
            )
            return AgentResult(
                status=AgentStatus.FAILED,
                data={"blocking_issues": 1, "warning_issues": 0, "issues": []},
            )

        orchestrator.security_agent.execute = mock_security
        orchestrator.checkov_agent.execute = AsyncMock(
            return_value=AgentResult(status=AgentStatus.SUCCESS)
        )
        orchestrator.policy_agent.execute = AsyncMock(
            return_value=AgentResult(status=AgentStatus.SUCCESS)
        )

        # Mock fix to modify files (simulating a bad fix)
        async def mock_fix(context):
            # Modify files (bad fix)
            context.generated_files["main.tf"] = "BROKEN CONTENT"
            (context.output_dir / "main.tf").write_text("BROKEN CONTENT")
            return AgentResult(status=AgentStatus.SUCCESS)

        orchestrator.code_gen_agent.execute_fix = mock_fix

        # Run security loop - should fail after max attempts due to rollback
        result = await orchestrator._run_security_loop(temp_context)

        # Should fail (max attempts exhausted with rollbacks)
        assert result is False
        assert temp_context.pipeline_failed is True

        # Files should be rolled back to original
        current_content = (temp_context.output_dir / "main.tf").read_text()
        assert current_content == original_content

    @pytest.mark.asyncio
    async def test_fix_attempt_counted_on_rollback(self, temp_context):
        """Rollback should count as a failed fix attempt."""
        orchestrator = PipelineOrchestrator(show_progress=False)
        temp_context.max_security_fix_attempts = 2

        # Mock validation: pass first, fail after fix
        validation_calls = [0]

        async def mock_validation(context):
            validation_calls[0] += 1
            if validation_calls[0] <= 1:
                return AgentResult(status=AgentStatus.SUCCESS)
            return AgentResult(status=AgentStatus.FAILED, errors=["Bad fix"])

        orchestrator.validation_agent.execute = mock_validation

        # Mock security to always find issues
        async def mock_security(context):
            context.add_security_issue(
                SecurityIssue(
                    severity=IssueSeverity.HIGH,
                    rule_id="TEST001",
                    description="Issue",
                    file_path="main.tf",
                    line_number=1,
                )
            )
            return AgentResult(
                status=AgentStatus.FAILED,
                data={"blocking_issues": 1, "warning_issues": 0, "issues": []},
            )

        orchestrator.security_agent.execute = mock_security
        orchestrator.checkov_agent.execute = AsyncMock(
            return_value=AgentResult(status=AgentStatus.SUCCESS)
        )
        orchestrator.policy_agent.execute = AsyncMock(
            return_value=AgentResult(status=AgentStatus.SUCCESS)
        )

        orchestrator.code_gen_agent.execute_fix = AsyncMock(
            return_value=AgentResult(status=AgentStatus.SUCCESS)
        )

        await orchestrator._run_security_loop(temp_context)

        # Fix attempts should have been incremented
        assert temp_context.security_fix_attempts > 0


class TestAgentEventCallbacks:
    """Test that agents emit events through callbacks."""

    def test_code_gen_agent_accepts_callback(self):
        """CodeGenerationAgent should accept event_callback."""
        from terragen.agents.code_generation import CodeGenerationAgent

        callback = MagicMock()
        agent = CodeGenerationAgent(event_callback=callback)
        assert agent.event_callback == callback

    def test_terragen_agent_emits_tool_events(self):
        """TerraGenAgent should emit events for tool calls."""
        from terragen.agent import TerraGenAgent

        events = []

        def capture_event(event):
            events.append(event)

        with tempfile.TemporaryDirectory() as tmpdir:
            agent = TerraGenAgent(
                output_dir=Path(tmpdir),
                event_callback=capture_event,
            )
            agent._emit_event("tool", "Writing file: main.tf")

        assert len(events) == 1
        assert events[0]["log"]["message"] == "Writing file: main.tf"


class TestSSEAuthentication:
    """Test SSE endpoint authentication with query params."""

    def test_get_user_from_query_token_missing(self):
        """Should raise HTTPException when token is missing."""
        from api.auth import get_user_from_query_token
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            get_user_from_query_token(None)

        assert exc_info.value.status_code == 401

    def test_get_user_from_query_token_invalid(self):
        """Should raise HTTPException for invalid token."""
        from api.auth import get_user_from_query_token
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            get_user_from_query_token("invalid-token")

        assert exc_info.value.status_code == 401

    def test_decode_jwt_token_valid(self):
        """decode_jwt_token should return User for valid token."""
        from api.auth import decode_jwt_token, create_jwt_token, GitUser

        # Create a valid token
        git_user = GitUser(
            id=123,
            username="testuser",
            email="test@example.com",
            provider="github",
        )
        token = create_jwt_token(git_user, "fake-git-token")

        # Decode it
        user = decode_jwt_token(token)

        assert user.username == "testuser"
        assert user.provider == "github"


class TestPipelineStages:
    """Test pipeline stage definitions."""

    def test_all_agents_have_stages(self):
        """All agents should have corresponding stage definitions."""
        from src.terragen.agents.orchestrator import PipelineOrchestrator

        orchestrator = PipelineOrchestrator()
        agent_names = [
            orchestrator.clarification_agent.name,
            orchestrator.code_gen_agent.name,
            orchestrator.validation_agent.name,
            orchestrator.security_agent.name,
            orchestrator.checkov_agent.name,
            orchestrator.policy_agent.name,
            orchestrator.cost_agent.name,
        ]

        # These should be trackable in agent_statuses
        for name in agent_names:
            assert name in orchestrator.agent_statuses

    def test_stage_status_tracking(self):
        """Agent statuses should be tracked correctly."""
        from terragen.agents.orchestrator import PipelineOrchestrator

        orchestrator = PipelineOrchestrator()

        # All should start as PENDING
        for status in orchestrator.agent_statuses.values():
            assert status == AgentStatus.PENDING


class TestLogEntryFormat:
    """Test log entry format for UI consumption."""

    def test_log_entry_has_required_fields(self):
        """Log entries should have timestamp, level, message."""
        callback = MagicMock()
        orchestrator = PipelineOrchestrator(session_callback=callback)

        orchestrator._emit_log("Test", level="info")

        log_entry = callback.call_args[0][0]["log"]
        assert "timestamp" in log_entry
        assert "level" in log_entry
        assert "message" in log_entry

    def test_log_entry_timestamp_format(self):
        """Timestamp should be ISO format with Z suffix."""
        callback = MagicMock()
        orchestrator = PipelineOrchestrator(session_callback=callback)

        orchestrator._emit_log("Test", level="info")

        timestamp = callback.call_args[0][0]["log"]["timestamp"]
        assert timestamp.endswith("Z")
        # Should be parseable
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

    def test_log_levels(self):
        """Log entries should support all levels."""
        callback = MagicMock()
        orchestrator = PipelineOrchestrator(session_callback=callback)

        for level in ["info", "success", "warning", "error"]:
            orchestrator._emit_log(f"Test {level}", level=level)

        assert callback.call_count == 4

    def test_log_with_details(self):
        """Log entries can include optional details."""
        callback = MagicMock()
        orchestrator = PipelineOrchestrator(session_callback=callback)

        orchestrator._emit_log("Test", level="error", details="Additional info")

        log_entry = callback.call_args[0][0]["log"]
        assert log_entry["details"] == "Additional info"

    def test_log_with_agent(self):
        """Log entries can include agent name."""
        callback = MagicMock()
        orchestrator = PipelineOrchestrator(session_callback=callback)

        orchestrator._emit_log("Test", level="info", agent="ValidationAgent")

        log_entry = callback.call_args[0][0]["log"]
        assert log_entry.get("agent") == "ValidationAgent"


class TestSessionUpdates:
    """Test session state updates for UI."""

    def test_current_agent_update(self):
        """Session should update current_agent."""
        callback = MagicMock()
        orchestrator = PipelineOrchestrator(session_callback=callback)

        orchestrator._update_session({"current_agent": "SecurityAgent"})

        callback.assert_called_with({"current_agent": "SecurityAgent"})

    def test_fix_attempt_update(self):
        """Session should update fix_attempt and max_fix_attempts."""
        callback = MagicMock()
        orchestrator = PipelineOrchestrator(session_callback=callback)

        orchestrator._update_session(
            {
                "fix_attempt": 2,
                "max_fix_attempts": 3,
            }
        )

        callback.assert_called_with(
            {
                "fix_attempt": 2,
                "max_fix_attempts": 3,
            }
        )


class TestFixableIssues:
    """Test has_fixable_issues method for validation and security issues."""

    def test_has_fixable_issues_with_validation_errors(self):
        """has_fixable_issues should return True when validation errors exist."""
        from terragen.agents.base import ValidationError

        context = PipelineContext(user_prompt="test", output_dir=Path("/tmp"))
        assert context.has_fixable_issues() is False

        context.add_validation_error(
            ValidationError(
                error_type="validate",
                message="Invalid reference",
                file_path="main.tf",
                line_number=10,
            )
        )

        assert context.has_fixable_issues() is True
        assert context.has_validation_errors() is True
        assert context.has_blocking_issues() is False

    def test_has_fixable_issues_with_security_issues(self):
        """has_fixable_issues should return True when blocking security issues exist."""
        context = PipelineContext(user_prompt="test", output_dir=Path("/tmp"))
        assert context.has_fixable_issues() is False

        context.add_security_issue(
            SecurityIssue(
                severity=IssueSeverity.HIGH,
                rule_id="TEST001",
                description="Security issue",
                file_path="main.tf",
                line_number=5,
            )
        )

        assert context.has_fixable_issues() is True
        assert context.has_blocking_issues() is True
        assert context.has_validation_errors() is False

    def test_has_fixable_issues_with_both(self):
        """has_fixable_issues should return True when both errors exist."""
        from terragen.agents.base import ValidationError

        context = PipelineContext(user_prompt="test", output_dir=Path("/tmp"))

        context.add_validation_error(
            ValidationError(
                error_type="validate",
                message="Syntax error",
            )
        )
        context.add_security_issue(
            SecurityIssue(
                severity=IssueSeverity.CRITICAL,
                rule_id="TEST002",
                description="Critical issue",
                file_path="main.tf",
                line_number=1,
            )
        )

        assert context.has_fixable_issues() is True
        assert context.has_validation_errors() is True
        assert context.has_blocking_issues() is True

    def test_get_issues_summary_includes_validation_errors(self):
        """get_issues_summary should include validation errors."""
        from terragen.agents.base import ValidationError

        context = PipelineContext(user_prompt="test", output_dir=Path("/tmp"))
        context.add_validation_error(
            ValidationError(
                error_type="validate",
                message="Reference to undeclared variable",
                file_path="main.tf",
                line_number=15,
            )
        )

        summary = context.get_issues_summary()

        assert "Validation Errors to Fix" in summary
        assert "Reference to undeclared variable" in summary
        assert "main.tf:15" in summary

    def test_get_issues_summary_includes_both(self):
        """get_issues_summary should include both validation and security issues."""
        from terragen.agents.base import ValidationError

        context = PipelineContext(user_prompt="test", output_dir=Path("/tmp"))

        context.add_validation_error(
            ValidationError(
                error_type="init",
                message="Provider not found",
            )
        )
        context.add_security_issue(
            SecurityIssue(
                severity=IssueSeverity.HIGH,
                rule_id="AWS001",
                description="S3 bucket not encrypted",
                file_path="s3.tf",
                line_number=10,
            )
        )

        summary = context.get_issues_summary()

        assert "Validation Errors to Fix" in summary
        assert "Provider not found" in summary
        assert "Security Issues to Fix" in summary
        assert "S3 bucket not encrypted" in summary

    def test_warning_issues_not_in_fixable(self):
        """Warning-level security issues should not trigger has_fixable_issues."""
        context = PipelineContext(user_prompt="test", output_dir=Path("/tmp"))

        context.add_security_issue(
            SecurityIssue(
                severity=IssueSeverity.LOW,
                rule_id="INFO001",
                description="Low severity info",
                file_path="main.tf",
                line_number=1,
            )
        )

        # LOW severity doesn't block pipeline
        assert context.has_fixable_issues() is False
        assert context.has_blocking_issues() is False
