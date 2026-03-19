"""Clarification agent for auto-detecting if questions are needed."""

import json
from typing import Any, Optional

from rich.console import Console
from rich.panel import Panel

from terragen.agents.base import AgentResult, AgentStatus, BaseAgent
from terragen.agents.context import PipelineContext
from terragen.config import LLM_MODELS, FALLBACK_ORDER
from terragen.llm import UnifiedLLMClient
from terragen.questions import (
    ask_clarifying_questions,
    build_clarification_context,
    generate_clarifying_questions_llm,
)


class ClarificationAgent(BaseAgent):
    """Agent that auto-detects if clarifying questions are needed.

    Analyzes the user prompt to determine if it contains enough information
    to generate quality Terraform code. If the prompt is complete, it
    extracts implicit requirements. Otherwise, it asks targeted questions.
    """

    name = "ClarificationAgent"
    description = "Auto-detects if clarifying questions are needed"
    is_gate = False  # Clarification doesn't block pipeline

    def __init__(self, console: Optional[Console] = None, log_callback: Optional[Any] = None):
        """Initialize the clarification agent."""
        super().__init__(console, log_callback)
        self.client = UnifiedLLMClient(
            fallback_order=FALLBACK_ORDER,
            models=LLM_MODELS,
        )

    async def execute(self, context: PipelineContext) -> AgentResult:
        """Execute clarification logic.

        Args:
            context: Pipeline context with user prompt.

        Returns:
            AgentResult with clarification data.
        """
        self._status = AgentStatus.RUNNING

        # Check if clarification should be skipped
        if context.skip_clarify:
            self._log_info("Skipping clarification (--skip-clarify)")
            context.clarification_skipped = True
            self._status = AgentStatus.SKIPPED
            return AgentResult(
                status=AgentStatus.SKIPPED,
                data={"reason": "User requested skip"},
            )

        # Assess if the prompt is complete enough
        self._log_info("Analyzing prompt completeness...")
        assessment = await self._assess_prompt_completeness(context)

        if assessment["is_complete"]:
            self._log_success("Prompt is detailed enough, skipping questions")
            context.clarifications = assessment["inferred_requirements"]
            context.clarification_skipped = True
            self._status = AgentStatus.SUCCESS
            return AgentResult(
                status=AgentStatus.SUCCESS,
                data={
                    "skipped_questions": True,
                    "inferred_requirements": assessment["inferred_requirements"],
                },
            )

        # Prompt needs clarification - ask questions
        self._log_info("Generating clarifying questions...")

        try:
            # Use the existing questions.py interactive flow
            answers = ask_clarifying_questions(context.user_prompt)

            # Update context with answers
            context.clarifications = answers

            # Update provider and region if answered
            if "provider" in answers:
                context.provider = answers["provider"]
            if "region" in answers:
                context.region = answers["region"]

            self._log_success("Clarification complete")
            self._status = AgentStatus.SUCCESS
            return AgentResult(
                status=AgentStatus.SUCCESS,
                data={"clarifications": answers},
            )

        except KeyboardInterrupt:
            self._log_warning("Clarification cancelled by user")
            self._status = AgentStatus.FAILED
            return AgentResult(
                status=AgentStatus.FAILED,
                errors=["User cancelled clarification"],
            )
        except Exception as e:
            self._log_error(f"Error during clarification: {e}")
            self._status = AgentStatus.FAILED
            return AgentResult(
                status=AgentStatus.FAILED,
                errors=[str(e)],
            )

    async def _assess_prompt_completeness(
        self, context: PipelineContext
    ) -> dict[str, Any]:
        """Assess if the user prompt contains enough detail.

        Uses the LLM to analyze the prompt and determine if it's
        detailed enough to generate quality Terraform code.

        Args:
            context: Pipeline context with user prompt.

        Returns:
            Dict with is_complete and inferred_requirements.
        """
        system_prompt = """You are an expert at analyzing infrastructure requirements.

Given a user's Terraform infrastructure request, determine:
1. Is the prompt detailed enough to generate production-quality Terraform code?
2. What requirements can be inferred from the prompt?

A prompt is "complete" if it specifies:
- Clear infrastructure components (what to create)
- Environment type (production/staging/dev) OR enough context to infer it
- Provider information (AWS/GCP/Azure) OR can be clearly inferred
- Key configuration choices are either specified or have obvious defaults

A prompt is "incomplete" if it:
- Is vague about what infrastructure to create
- Lacks critical security/sizing information for production use
- Requires user decisions that have no clear defaults

Return JSON with this structure:
{
  "is_complete": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation",
  "inferred_requirements": {
    "environment": "production/staging/development",
    "provider": "aws/gcp/azure",
    "security_level": "high/medium/low",
    "other_inferences": {}
  },
  "missing_information": ["list", "of", "missing", "items"]
}"""

        user_prompt = f"""Provider context: {context.provider}
Region context: {context.region}

User's infrastructure request:
{context.user_prompt}

Analyze this request and determine if it's complete enough for Terraform generation."""

        try:
            response = self.client.create_message(
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            response_text = response.get_text().strip()

            # Handle markdown code blocks
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            assessment = json.loads(response_text)

            # Default to requiring clarification if confidence is low
            if assessment.get("confidence", 0) < 0.7:
                assessment["is_complete"] = False

            return assessment

        except json.JSONDecodeError:
            # If we can't parse the response, default to asking questions
            self._log_warning("Could not parse assessment, will ask questions")
            return {
                "is_complete": False,
                "inferred_requirements": {},
                "missing_information": ["Unable to assess prompt"],
            }
        except Exception as e:
            self._log_warning(f"Assessment failed: {e}, will ask questions")
            return {
                "is_complete": False,
                "inferred_requirements": {},
                "missing_information": [str(e)],
            }

    def get_clarification_context(self, context: PipelineContext) -> str:
        """Get the formatted clarification context string.

        Args:
            context: Pipeline context with clarifications.

        Returns:
            Formatted context string for system prompt.
        """
        return build_clarification_context(context.clarifications)
