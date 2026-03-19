"""Code generation agent that wraps TerraGenAgent with fix mode."""

import asyncio
from pathlib import Path
from typing import Optional, Callable, Any

from rich.console import Console
from rich.panel import Panel

from terragen.agents.base import AgentResult, AgentStatus, BaseAgent
from terragen.agents.context import PipelineContext
from terragen.agent import TerraGenAgent, run_agent, run_interactive_session, EventCallback
from terragen.config import SYSTEM_PROMPT, LLM_MODELS, FALLBACK_ORDER
from terragen.questions import build_clarification_context, build_backend_context
from terragen.patterns import learn_patterns_from_repo as learn_patterns
from terragen.security_rules import build_security_prompt_section


# System prompt for fixing validation and security issues
FIX_ISSUES_SYSTEM_PROMPT = """You are TerraGen, an expert infrastructure engineer specializing in Terraform/OpenTofu.

## Your Task
Fix the validation errors and/or security issues identified in the Terraform code.

## CRITICAL: Efficiency Rules
1. **BATCH READS**: Read ALL affected files in ONE turn (parallel read_file calls)
2. **BATCH WRITES**: Write ALL fixed files in ONE turn (parallel write_file calls)
3. **MINIMIZE TURNS**: Fix should complete in 2-3 turns max:
   - Turn 1: Read all affected files
   - Turn 2: Write all fixed files
   - Turn 3: Validate (if needed)
4. **BE CONCISE**: No lengthy explanations - just fix and confirm

## Important Rules
1. READ the affected files first before making changes
2. Fix ONLY the issues identified - do not refactor or change other code
3. Follow the remediation guidance provided for each issue
4. Maintain the existing code style and structure
5. After fixing, the code should pass terraform validate

## Validation Error Fixes - Common Patterns

### Backend Configuration Errors
- If you see "backend" errors about S3 buckets, GCS buckets, or access denied:
  - COMMENT OUT the entire backend block in backend.tf
  - Replace with commented examples only
  - The user will configure their backend manually after the infrastructure exists
- NEVER leave an active backend block with placeholder values like "your-terraform-state-bucket"

### Syntax Errors
- Check for missing closing braces `}`
- Check for missing commas in lists
- Check for unclosed strings
- Fix typos in resource types and attribute names

### Reference Errors
- Ensure referenced resources exist (e.g., `aws_vpc.main` requires `resource "aws_vpc" "main"`)
- Ensure data sources are defined before being referenced
- Check variable names match their declarations
- Check module outputs are correctly referenced

### terraform.tfvars Validation Errors
- If a variable validation fails (e.g., "Bucket name must be between 3 and 63 characters"):
  - Fix the value in terraform.tfvars to pass validation
  - Use sensible example values, NOT empty strings ""
  - Examples:
    - bucket_name = "my-app-assets-bucket"
    - cluster_name = "my-eks-cluster"
    - db_name = "myapp_production"
- For sensitive variables, COMMENT OUT with instructions:
  - # db_password = "CHANGE_ME"  # Set this before applying

### Provider Errors
- Ensure provider is configured in `providers.tf` or `versions.tf`
- Check provider version constraints are valid
- Ensure required provider features are configured

### Output Errors ("Unsupported attribute", "This object does not have an attribute")
- These errors occur when outputs reference computed-only attributes that don't exist at plan time
- Common problematic attributes: `.status`, `.state`, `.instances`, `.capacity`, `.endpoint` (sometimes)
- FIX: Remove the problematic attribute from the output, or replace with a config-time attribute
- Example fix for EKS addons:
  ```hcl
  # WRONG - status doesn't exist at plan time
  output "addons" {
    value = { for k, v in aws_eks_addon.this : k => { status = v.status } }
  }
  # RIGHT - only use attributes that exist at plan time
  output "addons" {
    value = { for k, v in aws_eks_addon.this : k => {
      name    = v.addon_name
      version = v.addon_version
    }}
  }
  ```
- Use `try(value, null)` for attributes that might not exist

## Security Issue Fixes - Common Patterns

### S3 Buckets
- Add `server_side_encryption_configuration` with SSE-S3 or SSE-KMS
- Add `public_access_block` to prevent public access
- Enable `versioning`
- Add `logging` configuration if required

### Security Groups
- Never use `0.0.0.0/0` for ingress on sensitive ports (22, 3389, databases)
- Use specific CIDR ranges or security group references
- Add descriptions to all rules

### RDS/Databases
- Enable `storage_encrypted = true`
- Enable `deletion_protection = true` for production
- Use `multi_az = true` for high availability
- Enable `backup_retention_period` > 0

### IAM
- Use least-privilege policies
- Avoid using `*` in resources when possible
- Add conditions to policies

### General
- Add required tags
- Enable logging where applicable
- Use encrypted volumes"""


class CodeGenerationAgent(BaseAgent):
    """Agent that generates Terraform code using TerraGenAgent.

    Wraps the existing TerraGenAgent with additional capabilities:
    - Fix mode for addressing security issues
    - Integration with pipeline context
    - Progress tracking
    """

    name = "CodeGenerationAgent"
    description = "Generates Terraform code from requirements"
    is_gate = True  # Code must be generated to continue

    def __init__(
        self,
        console: Optional[Console] = None,
        max_turns: int = 50,  # Allow more turns for complex infrastructure
        event_callback: Optional[EventCallback] = None,
    ):
        """Initialize the code generation agent.

        Args:
            console: Rich console for output.
            max_turns: Maximum turns for the agent loop.
            event_callback: Callback for streaming events to UI.
        """
        super().__init__(console)
        self.max_turns = max_turns
        self.event_callback = event_callback

    async def execute(self, context: PipelineContext) -> AgentResult:
        """Execute code generation.

        Args:
            context: Pipeline context with requirements.

        Returns:
            AgentResult with generated files.
        """
        self._status = AgentStatus.RUNNING

        # Build the full prompt with context
        full_prompt = self._build_generation_prompt(context)

        # Ensure output directory exists
        context.output_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Run the agent in executor (it's synchronous)
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._run_generation(full_prompt, context),
            )

            if result == "Success":
                # Update context with generated files
                context.update_generated_files()
                self._log_success(f"Generated {len(context.generated_files)} files")
                self._status = AgentStatus.SUCCESS
                return AgentResult(
                    status=AgentStatus.SUCCESS,
                    data={"files": list(context.generated_files.keys())},
                )
            else:
                self._log_error(f"Generation failed: {result}")
                self._status = AgentStatus.FAILED
                return AgentResult(
                    status=AgentStatus.FAILED,
                    errors=[result],
                )

        except Exception as e:
            self._log_error(f"Error during generation: {e}")
            self._status = AgentStatus.FAILED
            return AgentResult(
                status=AgentStatus.FAILED,
                errors=[str(e)],
            )

    async def execute_fix(self, context: PipelineContext) -> AgentResult:
        """Execute fix mode for validation errors and security issues.

        Generates fixes for identified validation errors and security issues.

        Args:
            context: Pipeline context with validation errors and/or security issues.

        Returns:
            AgentResult with fix status.
        """
        self._status = AgentStatus.RUNNING

        if not context.has_fixable_issues():
            self._log_info("No issues to fix")
            return AgentResult(
                status=AgentStatus.SUCCESS,
                data={"message": "No issues to fix"},
            )

        # Build the fix prompt
        fix_prompt = self._build_fix_prompt(context)

        try:
            # Run the fix agent
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._run_fix(fix_prompt, context),
            )

            if result == "Success":
                # Update context with fixed files
                context.update_generated_files()
                self._log_success("Security fixes applied")
                self._status = AgentStatus.SUCCESS
                return AgentResult(
                    status=AgentStatus.SUCCESS,
                    data={"fixed_files": list(context.generated_files.keys())},
                )
            else:
                self._log_error(f"Fix failed: {result}")
                self._status = AgentStatus.FAILED
                return AgentResult(
                    status=AgentStatus.FAILED,
                    errors=[result],
                )

        except Exception as e:
            self._log_error(f"Error during fix: {e}")
            self._status = AgentStatus.FAILED
            return AgentResult(
                status=AgentStatus.FAILED,
                errors=[str(e)],
            )

    def _build_generation_prompt(self, context: PipelineContext) -> str:
        """Build the full generation prompt with all context.

        Args:
            context: Pipeline context.

        Returns:
            Complete prompt for code generation.
        """
        parts = [f"## User Request\n{context.user_prompt}"]

        # Add provider and region
        parts.append(f"\n## Configuration")
        parts.append(f"- Cloud Provider: {context.provider}")
        parts.append(f"- Region: {context.region}")
        parts.append(f"- Output Directory: {context.output_dir}")

        # Add clarification context
        if context.clarifications:
            clarification_context = build_clarification_context(context.clarifications)
            if clarification_context:
                parts.append(f"\n## Requirements\n{clarification_context}")

        # Add backend context
        if context.backend_config:
            backend_context = build_backend_context(context.backend_config)
            if backend_context:
                parts.append(backend_context)

        # Add learned patterns
        if context.learn_from:
            try:
                patterns = learn_patterns(context.learn_from)
                if patterns:
                    parts.append(f"\n## Learned Patterns\n{patterns}")
            except Exception:
                pass  # Ignore pattern learning failures

        # Add security rules for the provider (shift-left security)
        security_rules = build_security_prompt_section(context.provider)
        parts.append(security_rules)

        # Add instructions
        parts.append("""
## Instructions
1. Create all Terraform files in {output_dir}/ using ABSOLUTE paths
2. Include GitHub Actions workflows in .github/workflows/
3. After creating files, validate with terraform fmt, init, and validate
4. Follow ALL security rules above - code MUST pass tfsec, checkov, and policy scans
5. Start with providers.tf and versions.tf

Begin generating the Terraform code now.""".format(output_dir=context.output_dir))

        return "\n".join(parts)

    def _build_fix_prompt(self, context: PipelineContext) -> str:
        """Build the prompt for fixing validation and security issues.

        Args:
            context: Pipeline context with validation errors and/or security issues.

        Returns:
            Complete prompt for fixing issues.
        """
        parts = ["## Issues to Fix"]
        parts.append(context.get_issues_summary())

        parts.append(f"\n## Working Directory: {context.output_dir}")

        # List affected files
        affected_files = set()
        for error in context.validation_errors:
            if error.file_path:
                affected_files.add(error.file_path)
        for issue in context.get_blocking_issues():
            if issue.file_path:
                affected_files.add(issue.file_path)

        if affected_files:
            parts.append(f"\n## Affected Files: {', '.join(sorted(affected_files))}")

        parts.append("""
## Instructions
1. READ each affected file first before making changes
2. Fix ONLY the listed issues - do not refactor unrelated code
3. For validation errors: fix syntax, references, and configuration issues
4. For security issues: follow the remediation guidance provided
5. Maintain existing code style and structure
6. Run terraform fmt after making changes
7. Ensure all referenced resources and variables exist

Begin fixing the issues now.""")

        return "\n".join(parts)

    def _run_generation(self, prompt: str, context: PipelineContext) -> str:
        """Run the generation agent synchronously.

        Args:
            prompt: Full generation prompt.
            context: Pipeline context.

        Returns:
            Result string from agent.
        """
        if context.chat_mode:
            run_interactive_session(
                initial_prompt=prompt,
                output_dir=context.output_dir,
                system_prompt=SYSTEM_PROMPT,
            )
            return "Success"
        else:
            return run_agent(
                prompt=prompt,
                output_dir=context.output_dir,
                system_prompt=SYSTEM_PROMPT,
                max_turns=self.max_turns,
                event_callback=self.event_callback,
            )

    def _run_fix(self, prompt: str, context: PipelineContext) -> str:
        """Run the fix agent synchronously.

        Args:
            prompt: Fix prompt.
            context: Pipeline context.

        Returns:
            Result string from agent.
        """
        return run_agent(
            prompt=prompt,
            output_dir=context.output_dir,
            system_prompt=FIX_ISSUES_SYSTEM_PROMPT,
            max_turns=self.max_turns,
            event_callback=self.event_callback,
        )
