"""Validation agent for running terraform fmt/init/validate."""

import asyncio
import subprocess
from pathlib import Path
from typing import Any, Optional

from rich.console import Console

from terragen.agents.base import (
    AgentResult,
    AgentStatus,
    BaseAgent,
    ValidationError,
)
from terragen.agents.context import PipelineContext


class ValidationAgent(BaseAgent):
    """Agent that validates Terraform code using terraform CLI.

    Runs terraform fmt, init, validate, and optionally plan to ensure
    the generated code is syntactically correct and provider-valid.

    Validation steps:
    1. terraform fmt - Format check (auto-fixes)
    2. terraform init - Initialize providers
    3. terraform validate - Syntax and reference validation
    4. terraform plan - Provider-specific validation (optional, requires creds)
    """

    name = "ValidationAgent"
    description = "Validates Terraform code using fmt, init, validate, and plan"
    is_gate = True  # Validation must pass to continue

    def __init__(
        self,
        console: Optional[Console] = None,
        log_callback: Optional[Any] = None,
        run_plan: bool = True,  # Enable terraform plan by default
    ):
        """Initialize the validation agent.

        Args:
            console: Rich console for output.
            log_callback: Callback for streaming logs.
            run_plan: Whether to run terraform plan (requires cloud credentials).
        """
        super().__init__(console, log_callback)
        self.timeout = 120  # seconds
        self.plan_timeout = 180  # longer timeout for plan
        self.run_plan = run_plan

    async def execute(self, context: PipelineContext) -> AgentResult:
        """Execute Terraform validation.

        Args:
            context: Pipeline context with output directory.

        Returns:
            AgentResult with validation status.
        """
        self._status = AgentStatus.RUNNING
        context.clear_validation_errors()

        output_dir = context.output_dir
        if not output_dir.exists():
            self._log_error(f"Output directory does not exist: {output_dir}")
            return AgentResult(
                status=AgentStatus.FAILED,
                errors=["Output directory does not exist"],
            )

        # Check if there are any .tf files
        tf_files = list(output_dir.glob("*.tf"))
        if not tf_files:
            self._log_error("No Terraform files found in output directory")
            return AgentResult(
                status=AgentStatus.FAILED,
                errors=["No Terraform files found"],
            )

        errors: list[str] = []

        # Step 1: terraform fmt -check
        self._log_info("Running terraform fmt -check...")
        fmt_result = await self._run_terraform_fmt(output_dir)
        if fmt_result:
            for err in fmt_result:
                context.add_validation_error(err)
                errors.append(str(err.message))

        # Step 2: terraform init
        self._log_info("Running terraform init...")
        init_result = await self._run_terraform_init(output_dir)
        if init_result:
            for err in init_result:
                context.add_validation_error(err)
                errors.append(str(err.message))
            # If init fails, we can't run validate
            self._status = AgentStatus.FAILED
            return AgentResult(
                status=AgentStatus.FAILED,
                errors=errors,
                next_action="fix_validation",
            )

        # Step 3: terraform validate
        self._log_info("Running terraform validate...")
        validate_result = await self._run_terraform_validate(output_dir)
        if validate_result:
            for err in validate_result:
                context.add_validation_error(err)
                errors.append(str(err.message))

        # If validate failed, don't run plan
        if errors:
            self._log_error(f"Validation failed with {len(errors)} error(s)")
            self._status = AgentStatus.FAILED
            context.validation_passed = False
            return AgentResult(
                status=AgentStatus.FAILED,
                errors=errors,
                next_action="fix_validation",
            )

        # Step 4: terraform plan (optional, requires cloud credentials)
        if self.run_plan:
            self._log_info(f"Running terraform plan (provider: {context.provider})...")
            plan_result = await self._run_terraform_plan(output_dir, context.provider)
            if plan_result:
                for err in plan_result:
                    # Plan errors are often credential-related, log but don't always fail
                    if err.error_type == "plan_credentials":
                        self._log_warning(f"⚠️ Plan skipped: {err.message}")
                    else:
                        context.add_validation_error(err)
                        errors.append(str(err.message))

        # Determine final status
        if errors:
            self._log_error(f"Validation failed with {len(errors)} error(s)")
            self._status = AgentStatus.FAILED
            context.validation_passed = False
            return AgentResult(
                status=AgentStatus.FAILED,
                errors=errors,
                next_action="fix_validation",
            )

        self._log_success("Validation passed (fmt, init, validate, plan)")
        self._status = AgentStatus.SUCCESS
        context.validation_passed = True
        return AgentResult(status=AgentStatus.SUCCESS)

    async def _run_terraform_fmt(self, output_dir: Path) -> list[ValidationError]:
        """Run terraform fmt -check.

        Args:
            output_dir: Directory containing Terraform files.

        Returns:
            List of validation errors (empty if no errors).
        """
        errors = []
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["terraform", "fmt", "-check", "-diff"],
                    cwd=output_dir,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                ),
            )

            if result.returncode != 0:
                # Parse the diff output to find unformatted files
                if result.stdout:
                    # Auto-fix by running fmt without -check
                    fix_result = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: subprocess.run(
                            ["terraform", "fmt"],
                            cwd=output_dir,
                            capture_output=True,
                            text=True,
                            timeout=self.timeout,
                        ),
                    )
                    if fix_result.returncode == 0:
                        self._log_info("Auto-formatted Terraform files")
                    else:
                        errors.append(
                            ValidationError(
                                error_type="fmt",
                                message=f"Format check failed: {result.stdout[:500]}",
                            )
                        )

        except subprocess.TimeoutExpired:
            errors.append(
                ValidationError(
                    error_type="fmt",
                    message="terraform fmt timed out",
                )
            )
        except FileNotFoundError:
            errors.append(
                ValidationError(
                    error_type="fmt",
                    message="terraform CLI not found. Please install Terraform.",
                )
            )
        except Exception as e:
            errors.append(
                ValidationError(
                    error_type="fmt",
                    message=f"Error running terraform fmt: {str(e)}",
                )
            )

        return errors

    async def _run_terraform_init(self, output_dir: Path) -> list[ValidationError]:
        """Run terraform init.

        Args:
            output_dir: Directory containing Terraform files.

        Returns:
            List of validation errors (empty if no errors).
        """
        errors = []
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["terraform", "init", "-backend=false"],
                    cwd=output_dir,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                ),
            )

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or ""
                error_lower = error_msg.lower()

                # Check for specific backend configuration errors
                backend_error = self._detect_backend_error(error_lower)
                if backend_error:
                    self._log_warning(f"Backend configuration error: {backend_error}")
                    errors.append(
                        ValidationError(
                            error_type="init",
                            message=backend_error,
                            file_path="backend.tf",
                        )
                    )
                else:
                    errors.append(
                        ValidationError(
                            error_type="init",
                            message=(
                                error_msg[:500]
                                if error_msg
                                else "terraform init failed"
                            ),
                        )
                    )

        except subprocess.TimeoutExpired:
            errors.append(
                ValidationError(
                    error_type="init",
                    message="terraform init timed out",
                )
            )
        except FileNotFoundError:
            errors.append(
                ValidationError(
                    error_type="init",
                    message="terraform CLI not found. Please install Terraform.",
                )
            )
        except Exception as e:
            errors.append(
                ValidationError(
                    error_type="init",
                    message=f"Error running terraform init: {str(e)}",
                )
            )

        return errors

    async def _run_terraform_validate(self, output_dir: Path) -> list[ValidationError]:
        """Run terraform validate.

        Args:
            output_dir: Directory containing Terraform files.

        Returns:
            List of validation errors (empty if no errors).
        """
        errors = []
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["terraform", "validate", "-json"],
                    cwd=output_dir,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                ),
            )

            if result.returncode != 0:
                # Try to parse JSON output for detailed errors
                try:
                    import json

                    output = json.loads(result.stdout)
                    if not output.get("valid", True):
                        for diag in output.get("diagnostics", []):
                            if diag.get("severity") == "error":
                                file_path = ""
                                line_number = 0
                                if "range" in diag:
                                    file_path = diag["range"].get("filename", "")
                                    line_number = (
                                        diag["range"].get("start", {}).get("line", 0)
                                    )

                                errors.append(
                                    ValidationError(
                                        error_type="validate",
                                        message=diag.get("summary", "")
                                        + ": "
                                        + diag.get("detail", ""),
                                        file_path=file_path,
                                        line_number=line_number,
                                    )
                                )
                except json.JSONDecodeError:
                    # Fallback to plain text error
                    error_msg = result.stderr or result.stdout
                    errors.append(
                        ValidationError(
                            error_type="validate",
                            message=(
                                error_msg[:500]
                                if error_msg
                                else "terraform validate failed"
                            ),
                        )
                    )

        except subprocess.TimeoutExpired:
            errors.append(
                ValidationError(
                    error_type="validate",
                    message="terraform validate timed out",
                )
            )
        except FileNotFoundError:
            errors.append(
                ValidationError(
                    error_type="validate",
                    message="terraform CLI not found. Please install Terraform.",
                )
            )
        except Exception as e:
            errors.append(
                ValidationError(
                    error_type="validate",
                    message=f"Error running terraform validate: {str(e)}",
                )
            )

        return errors

    async def _run_terraform_plan(
        self, output_dir: Path, provider: str
    ) -> list[ValidationError]:
        """Run terraform plan to catch provider-specific errors.

        Args:
            output_dir: Directory containing Terraform files.
            provider: Cloud provider (aws, gcp, azure).

        Returns:
            List of validation errors (empty if no errors).
        """
        import os

        errors = []

        # Check if credentials are available
        has_creds = self._check_credentials(provider)
        if not has_creds:
            cred_help = {
                "aws": "Set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY or AWS_PROFILE",
                "gcp": "Set GOOGLE_APPLICATION_CREDENTIALS or run 'gcloud auth application-default login'",
                "azure": "Set ARM_CLIENT_ID/ARM_CLIENT_SECRET/ARM_TENANT_ID/ARM_SUBSCRIPTION_ID",
            }
            hint = cred_help.get(provider, "Configure cloud provider credentials")
            self._log_warning(f"No {provider.upper()} credentials found - {hint}")
            return [
                ValidationError(
                    error_type="plan_credentials",
                    message=f"No {provider.upper()} credentials configured. {hint}",
                )
            ]

        self._log_info(f"Found {provider.upper()} credentials, running plan...")

        try:
            # Run terraform plan with -detailed-exitcode
            # Exit code 0 = no changes, 1 = error, 2 = changes pending
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    [
                        "terraform",
                        "plan",
                        "-detailed-exitcode",
                        "-input=false",
                        "-no-color",
                    ],
                    cwd=output_dir,
                    capture_output=True,
                    text=True,
                    timeout=self.plan_timeout,
                ),
            )

            # Exit code 1 = error
            if result.returncode == 1:
                error_msg = result.stderr or result.stdout or ""
                self._log_error(f"terraform plan failed (exit code 1)")

                # Parse common plan errors
                plan_error = self._parse_plan_error(error_msg, provider)
                if plan_error:
                    errors.append(plan_error)
                else:
                    errors.append(
                        ValidationError(
                            error_type="plan",
                            message=f"terraform plan failed: {error_msg[:500]}",
                        )
                    )
            elif result.returncode == 2:
                # Exit code 2 = plan succeeded with changes (this is fine)
                self._log_success(
                    "✅ terraform plan succeeded (resources will be created)"
                )
            elif result.returncode == 0:
                self._log_success("✅ terraform plan succeeded (no changes needed)")

        except subprocess.TimeoutExpired:
            errors.append(
                ValidationError(
                    error_type="plan",
                    message="terraform plan timed out (this may be normal for large configs)",
                )
            )
        except FileNotFoundError:
            errors.append(
                ValidationError(
                    error_type="plan",
                    message="terraform CLI not found",
                )
            )
        except Exception as e:
            errors.append(
                ValidationError(
                    error_type="plan",
                    message=f"Error running terraform plan: {str(e)}",
                )
            )

        return errors

    def _check_credentials(self, provider: str) -> bool:
        """Check if cloud provider credentials are available.

        Args:
            provider: Cloud provider name.

        Returns:
            True if credentials appear to be configured.
        """
        import os

        if provider == "aws":
            # Check for AWS credentials with detailed logging
            has_access_key = bool(os.environ.get("AWS_ACCESS_KEY_ID"))
            has_profile = bool(os.environ.get("AWS_PROFILE"))
            has_role = bool(os.environ.get("AWS_ROLE_ARN"))
            has_creds_file = Path.home().joinpath(".aws/credentials").exists()

            self._log_info(
                f"AWS creds check: ACCESS_KEY={has_access_key}, PROFILE={has_profile}, ROLE={has_role}, FILE={has_creds_file}"
            )

            return any([has_access_key, has_profile, has_role, has_creds_file])
        elif provider == "gcp":
            return any(
                [
                    os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
                    os.environ.get("GOOGLE_CLOUD_PROJECT"),
                    os.environ.get("CLOUDSDK_CORE_PROJECT"),
                    Path.home()
                    .joinpath(".config/gcloud/application_default_credentials.json")
                    .exists(),
                ]
            )
        elif provider == "azure":
            return any(
                [
                    os.environ.get("ARM_CLIENT_ID"),
                    os.environ.get("ARM_SUBSCRIPTION_ID"),
                    os.environ.get("AZURE_SUBSCRIPTION_ID"),
                ]
            )

        return False

    def _parse_plan_error(
        self, error_msg: str, provider: str
    ) -> Optional[ValidationError]:
        """Parse terraform plan error to extract actionable info.

        Args:
            error_msg: Error message from terraform plan.
            provider: Cloud provider.

        Returns:
            ValidationError with parsed details, or None.
        """
        error_lower = error_msg.lower()

        # AWS-specific errors
        if provider == "aws":
            if (
                "invalidamid" in error_lower
                or "ami" in error_lower
                and "not found" in error_lower
            ):
                return ValidationError(
                    error_type="plan",
                    message='Invalid AMI ID. Use a data source to find valid AMIs: data "aws_ami" "example" { ... }',
                )
            if (
                "invalidsubnetid" in error_lower
                or "subnet" in error_lower
                and "not found" in error_lower
            ):
                return ValidationError(
                    error_type="plan",
                    message="Invalid subnet ID. Ensure subnets are created before referencing them.",
                )
            if (
                "invalidvpcid" in error_lower
                or "vpc" in error_lower
                and "not found" in error_lower
            ):
                return ValidationError(
                    error_type="plan",
                    message="Invalid VPC ID. Ensure VPC is created before referencing it.",
                )
            if "accessdenied" in error_lower or "unauthorized" in error_lower:
                return ValidationError(
                    error_type="plan",
                    message="AWS access denied. Check IAM permissions for Terraform.",
                )
            if "invalidparametervalue" in error_lower:
                return ValidationError(
                    error_type="plan",
                    message=f"Invalid parameter value: {error_msg[:300]}",
                )

        # GCP-specific errors
        if provider == "gcp":
            if "permission" in error_lower and "denied" in error_lower:
                return ValidationError(
                    error_type="plan",
                    message="GCP permission denied. Check service account permissions.",
                )
            if "quota" in error_lower:
                return ValidationError(
                    error_type="plan",
                    message="GCP quota exceeded. Request quota increase or reduce resources.",
                )

        # Azure-specific errors
        if provider == "azure":
            if "authorizationfailed" in error_lower:
                return ValidationError(
                    error_type="plan",
                    message="Azure authorization failed. Check service principal permissions.",
                )

        # Generic errors
        if "invalid" in error_lower and "reference" in error_lower:
            return ValidationError(
                error_type="plan",
                message="Invalid resource reference. Check that all referenced resources exist.",
            )

        return None

    def _detect_backend_error(self, error_lower: str) -> str | None:
        """Detect specific backend configuration errors from terraform init output.

        Args:
            error_lower: Lowercased error message from terraform init.

        Returns:
            User-friendly error message if backend error detected, None otherwise.
        """
        # S3 bucket errors
        if "s3" in error_lower or "bucket" in error_lower:
            if "nosuchbucket" in error_lower or "bucket does not exist" in error_lower:
                return "S3 bucket does not exist. Create the bucket first or comment out the backend block in backend.tf to use local state."
            if (
                "accessdenied" in error_lower
                or "forbidden" in error_lower
                or "access denied" in error_lower
            ):
                return "Access denied to S3 bucket. Check your AWS credentials and bucket permissions, or comment out the backend block."

        # DynamoDB table errors
        if "dynamodb" in error_lower:
            if (
                "resourcenotfoundexception" in error_lower
                or "table" in error_lower
                and "not found" in error_lower
            ):
                return "DynamoDB lock table does not exist. Create the table first or remove dynamodb_table from the backend config."
            if "accessdenied" in error_lower:
                return "Access denied to DynamoDB table. Check your AWS credentials and table permissions."

        # GCS bucket errors
        if "gcs" in error_lower or "storage.googleapis" in error_lower:
            if "notfound" in error_lower or "does not exist" in error_lower:
                return "GCS bucket does not exist. Create the bucket first or comment out the backend block in backend.tf."
            if "forbidden" in error_lower or "permission" in error_lower:
                return "Access denied to GCS bucket. Check your Google Cloud credentials and bucket permissions."

        # Azure storage errors
        if "azurerm" in error_lower or "azure" in error_lower:
            if (
                "containernotfound" in error_lower
                or "container" in error_lower
                and "not found" in error_lower
            ):
                return "Azure storage container does not exist. Create the container first or comment out the backend block."
            if "storageaccountnotfound" in error_lower:
                return "Azure storage account does not exist. Create the storage account first."
            if "authorizationfailed" in error_lower or "forbidden" in error_lower:
                return "Access denied to Azure storage. Check your Azure credentials and permissions."

        # Terraform Cloud errors
        if "terraform cloud" in error_lower or "app.terraform.io" in error_lower:
            if "organization" in error_lower and (
                "not found" in error_lower or "does not exist" in error_lower
            ):
                return "Terraform Cloud organization not found. Check your organization name or create one."
            if "workspace" in error_lower and (
                "not found" in error_lower or "does not exist" in error_lower
            ):
                return (
                    "Terraform Cloud workspace not found. Create the workspace first."
                )
            if "unauthorized" in error_lower or "token" in error_lower:
                return "Terraform Cloud authentication failed. Check your TF_TOKEN_app_terraform_io environment variable."

        # Generic backend errors
        if "backend" in error_lower and (
            "forbidden" in error_lower
            or "access" in error_lower
            or "denied" in error_lower
        ):
            return "Backend configuration error: Access denied. Check your credentials and permissions, or comment out the backend block in backend.tf."

        return None
