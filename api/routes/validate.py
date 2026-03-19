"""Validate and cost estimation routes."""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user, User
from ..logging_config import log_validate, log_error

router = APIRouter(prefix="/validate", tags=["validate"])


class ValidateRequest(BaseModel):
    """Validate request with inline files."""

    files: dict[str, str]  # filename -> content


class ValidateResponse(BaseModel):
    """Validation response."""

    valid: bool
    format_ok: bool
    errors: list[str]
    warnings: list[str]


class CostRequest(BaseModel):
    """Cost estimation request."""

    files: dict[str, str]


class CostResponse(BaseModel):
    """Cost estimation response."""

    monthly_cost: Optional[str] = None
    breakdown: Optional[list[dict]] = None
    error: Optional[str] = None


class PlanRequest(BaseModel):
    """Terraform plan request."""

    files: dict[str, str]


class PlanResponse(BaseModel):
    """Terraform plan response."""

    success: bool
    plan_output: Optional[str] = None
    resource_changes: Optional[list[dict]] = None
    error: Optional[str] = None


class SecurityRequest(BaseModel):
    """Security scan request."""

    files: dict[str, str]


class SecurityResponse(BaseModel):
    """Security scan response."""

    issues: list[dict]
    passed: int
    failed: int


@router.post("/", response_model=ValidateResponse)
async def validate(
    request: ValidateRequest,
    user: User = Depends(get_current_user),
):
    """Validate Terraform configuration."""
    # Create temp directory with files
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Write files
        for name, content in request.files.items():
            file_path = tmppath / name
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)

        errors = []
        warnings = []
        format_ok = True

        # Check format
        fmt_process = await asyncio.create_subprocess_exec(
            "terraform",
            "fmt",
            "-check",
            "-diff",
            cwd=str(tmppath),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        fmt_stdout, fmt_stderr = await fmt_process.communicate()

        if fmt_process.returncode != 0:
            format_ok = False
            warnings.append("Terraform formatting issues detected")

        # Initialize
        init_process = await asyncio.create_subprocess_exec(
            "terraform",
            "init",
            "-backend=false",
            cwd=str(tmppath),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, init_stderr = await init_process.communicate()

        if init_process.returncode != 0:
            errors.append(f"Terraform init failed: {init_stderr.decode()}")
            return ValidateResponse(
                valid=False,
                format_ok=format_ok,
                errors=errors,
                warnings=warnings,
            )

        # Validate
        validate_process = await asyncio.create_subprocess_exec(
            "terraform",
            "validate",
            "-json",
            cwd=str(tmppath),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        validate_stdout, _ = await validate_process.communicate()

        import json

        try:
            result = json.loads(validate_stdout.decode())
            valid = result.get("valid", False)

            for diag in result.get("diagnostics", []):
                if diag.get("severity") == "error":
                    errors.append(diag.get("summary", "Unknown error"))
                else:
                    warnings.append(diag.get("summary", "Unknown warning"))

        except json.JSONDecodeError:
            valid = validate_process.returncode == 0

        log_validate("Terraform validation", valid=valid, errors=len(errors))

        return ValidateResponse(
            valid=valid,
            format_ok=format_ok,
            errors=errors,
            warnings=warnings,
        )


@router.post("/plan", response_model=PlanResponse)
async def plan(
    request: PlanRequest,
    user: User = Depends(get_current_user),
):
    """Run Terraform plan to preview changes."""
    import json

    # Create temp directory with files
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Write files
        for name, content in request.files.items():
            file_path = tmppath / name
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)

        # Initialize
        init_process = await asyncio.create_subprocess_exec(
            "terraform",
            "init",
            "-backend=false",
            cwd=str(tmppath),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, init_stderr = await init_process.communicate()

        if init_process.returncode != 0:
            return PlanResponse(
                success=False,
                error=f"Terraform init failed: {init_stderr.decode()}",
            )

        # Run plan with JSON output
        plan_process = await asyncio.create_subprocess_exec(
            "terraform",
            "plan",
            "-no-color",
            "-out=tfplan",
            cwd=str(tmppath),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        plan_stdout, plan_stderr = await plan_process.communicate()

        if plan_process.returncode != 0:
            return PlanResponse(
                success=False,
                error=plan_stderr.decode() or plan_stdout.decode(),
            )

        # Get plan in JSON format for resource changes
        show_process = await asyncio.create_subprocess_exec(
            "terraform",
            "show",
            "-json",
            "tfplan",
            cwd=str(tmppath),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        show_stdout, _ = await show_process.communicate()

        resource_changes = []
        if show_process.returncode == 0 and show_stdout:
            try:
                plan_json = json.loads(show_stdout.decode())
                for change in plan_json.get("resource_changes", []):
                    actions = change.get("change", {}).get("actions", [])
                    if actions and actions != ["no-op"]:
                        resource_changes.append(
                            {
                                "address": change.get("address", ""),
                                "type": change.get("type", ""),
                                "name": change.get("name", ""),
                                "actions": actions,
                            }
                        )
            except json.JSONDecodeError:
                pass

        return PlanResponse(
            success=True,
            plan_output=plan_stdout.decode(),
            resource_changes=resource_changes,
        )


@router.post("/cost", response_model=CostResponse)
async def estimate_cost(
    request: CostRequest,
    user: User = Depends(get_current_user),
):
    """Estimate infrastructure cost using Infracost."""
    from ..config import get_settings

    settings = get_settings()

    if not settings.infracost_api_key:
        return CostResponse(error="Infracost API key not configured")

    # Create temp directory with files
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Write files
        for name, content in request.files.items():
            file_path = tmppath / name
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)

        # Initialize terraform first
        tf_env = {**os.environ, "TF_LOG": ""}
        init_process = await asyncio.create_subprocess_exec(
            "terraform",
            "init",
            "-backend=false",
            cwd=str(tmppath),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=tf_env,
        )
        await init_process.communicate()

        # Run infracost
        cost_env = {**os.environ, "INFRACOST_API_KEY": settings.infracost_api_key}
        cost_process = await asyncio.create_subprocess_exec(
            "infracost",
            "breakdown",
            "--path",
            str(tmppath),
            "--format",
            "json",
            cwd=str(tmppath),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=cost_env,
        )
        cost_stdout, cost_stderr = await cost_process.communicate()

        if cost_process.returncode != 0:
            return CostResponse(error=f"Infracost failed: {cost_stderr.decode()}")

        import json

        try:
            result = json.loads(cost_stdout.decode())

            monthly_cost = result.get("totalMonthlyCost", "0.00")
            breakdown = []

            for project in result.get("projects", []):
                for resource in project.get("breakdown", {}).get("resources", []):
                    if float(resource.get("monthlyCost", 0) or 0) > 0:
                        breakdown.append(
                            {
                                "name": resource["name"],
                                "monthly_cost": resource["monthlyCost"],
                            }
                        )

            return CostResponse(
                monthly_cost=f"${monthly_cost}",
                breakdown=breakdown,
            )

        except json.JSONDecodeError:
            return CostResponse(error="Failed to parse Infracost output")


@router.post("/security", response_model=SecurityResponse)
async def security_scan(
    request: SecurityRequest,
    user: User = Depends(get_current_user),
):
    """Run security scan on Terraform configuration using tfsec, checkov, and conftest."""
    import json

    # Create temp directory with files
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Write files
        for name, content in request.files.items():
            file_path = tmppath / name
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)

        issues = []
        passed = 0
        failed = 0

        # 1. Run tfsec
        try:
            tfsec_process = await asyncio.create_subprocess_exec(
                "tfsec",
                str(tmppath),
                "--format",
                "json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            tfsec_stdout, _ = await tfsec_process.communicate()

            if tfsec_process.returncode != 127:
                try:
                    result = json.loads(tfsec_stdout.decode())
                    for finding in result.get("results", []):
                        severity = finding.get("severity", "UNKNOWN").upper()
                        location = finding.get("location", {})
                        file_name = location.get("filename", "")
                        # Get just filename from path
                        if "/" in file_name:
                            file_name = file_name.split("/")[-1]
                        issues.append(
                            {
                                "severity": severity,
                                "rule_id": finding.get("rule_id", ""),
                                "description": finding.get("description", ""),
                                "file_path": file_name,
                                "line_number": location.get("start_line", 0),
                                "scanner": "tfsec",
                            }
                        )
                        if severity in ["CRITICAL", "HIGH"]:
                            failed += 1
                        else:
                            passed += 1
                except json.JSONDecodeError:
                    pass
        except FileNotFoundError:
            pass

        # 2. Run checkov
        try:
            checkov_process = await asyncio.create_subprocess_exec(
                "checkov",
                "-d",
                str(tmppath),
                "-o",
                "json",
                "--quiet",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            checkov_stdout, _ = await checkov_process.communicate()

            if checkov_process.returncode != 127:
                try:
                    # Checkov can output multiple JSON objects, take the first
                    output = checkov_stdout.decode().strip()
                    if output.startswith("["):
                        results = json.loads(output)
                    else:
                        results = [json.loads(output)]

                    for result in results:
                        if isinstance(result, dict):
                            for check in result.get("results", {}).get(
                                "failed_checks", []
                            ):
                                severity = check.get("check_result", {}).get(
                                    "severity", "MEDIUM"
                                )
                                if not severity:
                                    severity = "MEDIUM"
                                severity = severity.upper()
                                file_path = check.get("file_path", "")
                                if "/" in file_path:
                                    file_path = file_path.split("/")[-1]
                                issues.append(
                                    {
                                        "severity": severity,
                                        "rule_id": check.get("check_id", ""),
                                        "description": check.get("check_name", ""),
                                        "file_path": file_path,
                                        "line_number": (
                                            check.get("file_line_range", [0])[0]
                                            if check.get("file_line_range")
                                            else 0
                                        ),
                                        "scanner": "checkov",
                                    }
                                )
                                if severity in ["CRITICAL", "HIGH"]:
                                    failed += 1
                                else:
                                    passed += 1
                except json.JSONDecodeError:
                    pass
        except FileNotFoundError:
            pass

        # 3. Run conftest (if policies exist)
        try:
            conftest_process = await asyncio.create_subprocess_exec(
                "conftest",
                "test",
                str(tmppath),
                "--output",
                "json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            conftest_stdout, _ = await conftest_process.communicate()

            if conftest_process.returncode != 127:
                try:
                    results = json.loads(conftest_stdout.decode())
                    for result in results:
                        file_path = result.get("filename", "")
                        if "/" in file_path:
                            file_path = file_path.split("/")[-1]
                        for failure in result.get("failures", []):
                            issues.append(
                                {
                                    "severity": "HIGH",
                                    "rule_id": "OPA-POLICY",
                                    "description": failure.get(
                                        "msg", "Policy violation"
                                    ),
                                    "file_path": file_path,
                                    "line_number": 0,
                                    "scanner": "conftest",
                                }
                            )
                            failed += 1
                        for warning in result.get("warnings", []):
                            issues.append(
                                {
                                    "severity": "MEDIUM",
                                    "rule_id": "OPA-POLICY",
                                    "description": warning.get("msg", "Policy warning"),
                                    "file_path": file_path,
                                    "line_number": 0,
                                    "scanner": "conftest",
                                }
                            )
                            passed += 1
                except json.JSONDecodeError:
                    pass
        except FileNotFoundError:
            pass

        # If no scanners available, do basic pattern checks
        if not issues and failed == 0 and passed == 0:
            for name, content in request.files.items():
                if "0.0.0.0/0" in content:
                    issues.append(
                        {
                            "severity": "HIGH",
                            "rule_id": "NETWORK-001",
                            "description": "Potential open access (0.0.0.0/0) detected",
                            "file_path": name,
                            "line_number": 0,
                            "scanner": "pattern",
                        }
                    )
                    failed += 1

        return SecurityResponse(
            issues=issues,
            passed=passed,
            failed=failed,
        )
