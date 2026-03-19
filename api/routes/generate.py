"""Generate routes."""

import tempfile
import shutil
import time
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio
import json
import uuid

from ..auth import get_current_user, get_user_from_query_token, User
from ..config import get_settings
from ..logging_config import log_generate, log_agent, log_error

router = APIRouter(prefix="/generate", tags=["generate"])


class BackendConfig(BaseModel):
    """Backend configuration details."""

    type: str
    # S3 backend
    bucket: Optional[str] = None
    key: Optional[str] = None
    region: Optional[str] = None
    dynamodb_table: Optional[str] = None
    # GCS backend
    prefix: Optional[str] = None
    # Azure backend
    resource_group_name: Optional[str] = None
    storage_account_name: Optional[str] = None
    container_name: Optional[str] = None
    # Terraform Cloud
    organization: Optional[str] = None
    workspace: Optional[str] = None


class GenerateRequest(BaseModel):
    """Generate infrastructure request."""

    prompt: str
    provider: str = "aws"
    region: Optional[str] = None
    backend: Optional[str] = None
    backendConfig: Optional[BackendConfig] = None
    options: Optional[dict] = None
    clarifications: Optional[dict] = None  # Production options, service configs
    skip_clarify: bool = True  # API defaults to skip clarify (non-interactive)
    skip_cost: bool = False
    skip_security: bool = True  # Skip auto security scan - user runs manually from options
    max_security_fixes: int = 3
    use_pipeline: bool = True  # Use multi-agent pipeline


class AnalyzeImageRequest(BaseModel):
    """Analyze architecture diagram to extract requirements."""

    image_data: str  # Base64 encoded image (with or without data URI prefix)
    additional_context: Optional[str] = None


class AnalyzeImageResponse(BaseModel):
    """Response from diagram analysis."""

    analysis: str  # Detailed analysis text
    cloud_provider: Optional[str] = None  # Detected provider (aws/gcp/azure)
    components: list[dict] = []  # Extracted components
    networking: Optional[str] = None
    data_flow: Optional[str] = None
    additional_requirements: Optional[str] = None


class GenerateFromImageRequest(BaseModel):
    """Generate infrastructure from architecture diagram."""

    image_data: str  # Base64 encoded image (with or without data URI prefix)
    additional_context: Optional[str] = None  # User's additional requirements
    provider: str = "aws"
    region: Optional[str] = None
    backend: Optional[str] = None
    backendConfig: Optional[BackendConfig] = None
    skip_cost: bool = False
    max_security_fixes: int = 3
    # Optional: use pre-analyzed results instead of re-analyzing
    confirmed_analysis: Optional[str] = None


class GenerateResponse(BaseModel):
    """Generate response."""

    session_id: str
    status: str
    files: Optional[dict] = None
    cost_estimate: Optional[dict] = None
    security_issues: Optional[list] = None
    validation_errors: Optional[list] = None
    plan: Optional[str] = None
    pipeline_summary: Optional[dict] = None
    current_agent: Optional[str] = None
    fix_attempt: Optional[int] = None
    max_fix_attempts: Optional[int] = None
    logs: Optional[list] = None
    error: Optional[str] = None


class UpdateFilesRequest(BaseModel):
    """Request to update session files."""

    files: dict


class ClarifyRequest(BaseModel):
    """Request for clarifying questions."""

    prompt: str
    provider: str = "aws"


class ClarifyResponse(BaseModel):
    """Clarifying questions response."""

    questions: list[dict]


# In-memory session storage (replace with Redis for production)
sessions: dict = {}


@router.post("/clarify", response_model=ClarifyResponse)
async def get_clarifying_questions(
    request: ClarifyRequest,
    user: User = Depends(get_current_user),
):
    """Get LLM-generated clarifying questions for the prompt."""
    import os
    import sys

    # Check API key is configured
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY not configured. Add it to .env file.",
        )

    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

    from terragen.questions import generate_clarifying_questions_llm

    # Run LLM call in executor since it's blocking
    loop = asyncio.get_event_loop()
    questions = await loop.run_in_executor(
        None,
        lambda: generate_clarifying_questions_llm(request.prompt, request.provider)
    )

    log_generate(
        f"LLM generated {len(questions)} clarify questions",
        session_id="n/a",
        provider=request.provider,
    )

    return ClarifyResponse(questions=questions)


@router.post("/", response_model=GenerateResponse)
async def generate(
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
):
    """Start infrastructure generation.

    Uses the multi-agent pipeline by default, which includes:
    - Clarification (auto-detect mode)
    - Code generation
    - Validation (terraform fmt/init/validate)
    - Security scanning (tfsec, checkov, conftest)
    - Automatic fix loop for security issues
    - Cost estimation (infracost)
    """
    import os

    # Check API key is configured
    has_api_key = any([
        os.environ.get("ANTHROPIC_API_KEY"),
        os.environ.get("XAI_API_KEY"),
        os.environ.get("OPENAI_API_KEY"),
    ])
    if not has_api_key:
        raise HTTPException(
            status_code=500,
            detail="No LLM API key configured. Set ANTHROPIC_API_KEY, XAI_API_KEY, or OPENAI_API_KEY.",
        )

    session_id = str(uuid.uuid4())

    # Create temp directory for output
    output_dir = Path(tempfile.mkdtemp(prefix="terragen_"))

    sessions[session_id] = {
        "status": "pending",
        "output_dir": str(output_dir),
        "user": user.username,
        "request": request.model_dump(),
        "started_at": time.time(),
        "current_agent": None,
        "security_issues": None,  # None = no scan run; [] = scan run with 0 issues
        "validation_errors": [],
        "cost_estimate": None,
        "fix_attempt": 0,
        "max_fix_attempts": request.max_security_fixes,
        "logs": [],
    }

    log_generate(
        "Generation started",
        session_id=session_id,
        provider=request.provider,
        user=user.username,
        prompt=request.prompt[:50],
        use_pipeline=request.use_pipeline,
    )

    # Start generation in background
    background_tasks.add_task(
        run_generation,
        session_id,
        request,
        output_dir,
        user.username,
    )

    return GenerateResponse(
        session_id=session_id,
        status="pending",
    )


@router.post("/analyze-image", response_model=AnalyzeImageResponse)
async def analyze_image(
    request: AnalyzeImageRequest,
    user: User = Depends(get_current_user),
):
    """Analyze an architecture diagram and extract requirements.

    Returns the analysis for user confirmation before generating code.
    """
    import os
    import sys
    import re

    # Check API key is configured (requires Anthropic for vision)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY is required for image analysis.",
        )

    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

    from terragen.vision import analyze_diagram

    log_generate(
        "Image analysis started",
        session_id="n/a",
        user=user.username,
    )

    # Run diagram analysis in executor (blocking call)
    loop = asyncio.get_event_loop()
    try:
        analysis_result = await loop.run_in_executor(
            None,
            lambda: analyze_diagram(
                request.image_data,
                request.additional_context,
            )
        )
    except Exception as e:
        log_error("Image analysis failed", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to analyze image: {str(e)}")

    analysis_text = analysis_result["analysis"]

    # Parse the analysis to extract structured data
    cloud_provider = None
    components = []
    networking = None
    data_flow = None
    additional_requirements = None

    # Extract cloud provider
    provider_match = re.search(r"## Cloud Provider\s*\n+([^\n#]+)", analysis_text, re.IGNORECASE)
    if provider_match:
        provider_text = provider_match.group(1).strip().lower()
        if "aws" in provider_text:
            cloud_provider = "aws"
        elif "gcp" in provider_text or "google" in provider_text:
            cloud_provider = "gcp"
        elif "azure" in provider_text:
            cloud_provider = "azure"

    # Extract components section
    components_match = re.search(r"## Components\s*\n+(.*?)(?=##|$)", analysis_text, re.IGNORECASE | re.DOTALL)
    if components_match:
        components_text = components_match.group(1).strip()
        # Parse bullet points or numbered items
        for line in components_text.split("\n"):
            line = line.strip()
            if line and (line.startswith("-") or line.startswith("*") or line[0].isdigit()):
                # Clean up the line
                clean_line = re.sub(r"^[-*\d.)\s]+", "", line).strip()
                if clean_line:
                    # Try to extract component name and description
                    if ":" in clean_line:
                        name, desc = clean_line.split(":", 1)
                        components.append({"name": name.strip(), "description": desc.strip()})
                    else:
                        components.append({"name": clean_line, "description": ""})

    # Extract networking section
    networking_match = re.search(r"## Networking\s*\n+(.*?)(?=##|$)", analysis_text, re.IGNORECASE | re.DOTALL)
    if networking_match:
        networking = networking_match.group(1).strip()

    # Extract data flow section
    dataflow_match = re.search(r"## Data Flow\s*\n+(.*?)(?=##|$)", analysis_text, re.IGNORECASE | re.DOTALL)
    if dataflow_match:
        data_flow = dataflow_match.group(1).strip()

    # Extract additional requirements
    additional_match = re.search(r"## Additional Requirements\s*\n+(.*?)(?=##|$)", analysis_text, re.IGNORECASE | re.DOTALL)
    if additional_match:
        additional_requirements = additional_match.group(1).strip()

    log_generate(
        "Image analysis completed",
        session_id="n/a",
        user=user.username,
        provider=cloud_provider,
        components=len(components),
    )

    return AnalyzeImageResponse(
        analysis=analysis_text,
        cloud_provider=cloud_provider,
        components=components,
        networking=networking,
        data_flow=data_flow,
        additional_requirements=additional_requirements,
    )


@router.post("/from-image", response_model=GenerateResponse)
async def generate_from_image(
    request: GenerateFromImageRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
):
    """Generate infrastructure from an architecture diagram.

    Analyzes the uploaded diagram using Claude's vision capabilities,
    then generates Terraform code based on the analysis.
    """
    import os
    import sys

    # Check API key is configured (requires Anthropic for vision)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY is required for image analysis.",
        )

    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

    from terragen.vision import analyze_diagram

    session_id = str(uuid.uuid4())

    # Create temp directory for output
    output_dir = Path(tempfile.mkdtemp(prefix="terragen_"))

    sessions[session_id] = {
        "status": "pending",
        "output_dir": str(output_dir),
        "user": user.username,
        "request": request.model_dump(),
        "started_at": time.time(),
        "current_agent": "vision",
        "security_issues": None,  # None = no scan run; [] = scan run with 0 issues
        "validation_errors": [],
        "cost_estimate": None,
        "fix_attempt": 0,
        "max_fix_attempts": request.max_security_fixes,
        "logs": [],
    }

    log_generate(
        "Image-based generation started",
        session_id=session_id,
        provider=request.provider,
        user=user.username,
    )

    # Start generation in background
    background_tasks.add_task(
        run_image_generation,
        session_id,
        request,
        output_dir,
        user.username,
    )

    return GenerateResponse(
        session_id=session_id,
        status="pending",
    )


async def run_image_generation(
    session_id: str,
    request: GenerateFromImageRequest,
    output_dir: Path,
    username: str,
):
    """Run image-based generation: analyze diagram then generate code."""
    start_time = time.time()

    try:
        sessions[session_id]["status"] = "running"

        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

        from terragen.vision import analyze_diagram, build_terraform_prompt
        from terragen.config import PROVIDER_REGIONS

        # Check if we have pre-confirmed analysis (user already reviewed)
        if request.confirmed_analysis:
            sessions[session_id]["logs"].append({
                "timestamp": time.strftime("%H:%M:%S"),
                "level": "info",
                "agent": "VisionAgent",
                "message": "Using confirmed requirements from diagram analysis",
            })

            # Build the Terraform prompt from the confirmed analysis
            terraform_prompt = build_terraform_prompt(
                request.confirmed_analysis,
                request.additional_context,
            )
            sessions[session_id]["diagram_analysis"] = request.confirmed_analysis

        else:
            # Run fresh diagram analysis
            sessions[session_id]["logs"].append({
                "timestamp": time.strftime("%H:%M:%S"),
                "level": "info",
                "agent": "VisionAgent",
                "message": "Analyzing architecture diagram...",
            })

            # Run diagram analysis in executor (blocking call)
            loop = asyncio.get_event_loop()
            analysis_result = await loop.run_in_executor(
                None,
                lambda: analyze_diagram(
                    request.image_data,
                    request.additional_context,
                )
            )

            sessions[session_id]["logs"].append({
                "timestamp": time.strftime("%H:%M:%S"),
                "level": "success",
                "agent": "VisionAgent",
                "message": "Diagram analysis complete",
            })

            terraform_prompt = analysis_result["prompt"]
            sessions[session_id]["diagram_analysis"] = analysis_result["analysis"]

        # Get region
        region = request.region
        if not region:
            region = PROVIDER_REGIONS.get(request.provider, {}).get(
                "default", "us-east-1"
            )

        # Build backend config
        backend_config = None
        if request.backend and request.backend != "local":
            if request.backendConfig:
                backend_config = request.backendConfig.model_dump(exclude_none=True)
            else:
                backend_config = {"type": request.backend}

        # Use the multi-agent pipeline with the generated prompt
        from terragen.agents.context import PipelineContext
        from terragen.agents.orchestrator import PipelineOrchestrator

        # Create pipeline context with the Terraform generation prompt
        context = PipelineContext(
            user_prompt=terraform_prompt,
            provider=request.provider,
            region=region,
            output_dir=output_dir,
            skip_clarify=True,  # Skip clarify since diagram provides the spec
            skip_cost=request.skip_cost,
            skip_security=True,  # User runs security scan manually from options
            max_security_fix_attempts=request.max_security_fixes,
            chat_mode=False,
            backend_config=backend_config,
        )

        # Callback to update session state
        def session_callback(updates: dict):
            if "log" in updates:
                if "logs" not in sessions[session_id]:
                    sessions[session_id]["logs"] = []
                sessions[session_id]["logs"].append(updates["log"])
            elif "completed_agent" in updates:
                if "completed_agents" not in sessions[session_id]:
                    sessions[session_id]["completed_agents"] = []
                agent_name = updates["completed_agent"]
                if agent_name not in sessions[session_id]["completed_agents"]:
                    sessions[session_id]["completed_agents"].append(agent_name)
                if "failed_agents" in sessions[session_id] and agent_name in sessions[session_id]["failed_agents"]:
                    sessions[session_id]["failed_agents"].remove(agent_name)
            elif "skipped_agent" in updates:
                if "skipped_agents" not in sessions[session_id]:
                    sessions[session_id]["skipped_agents"] = []
                sessions[session_id]["skipped_agents"].append(updates["skipped_agent"])
            elif "failed_agent" in updates:
                if "failed_agents" not in sessions[session_id]:
                    sessions[session_id]["failed_agents"] = []
                agent_name = updates["failed_agent"]
                if "completed_agents" not in sessions[session_id] or agent_name not in sessions[session_id]["completed_agents"]:
                    if agent_name not in sessions[session_id]["failed_agents"]:
                        sessions[session_id]["failed_agents"].append(agent_name)
            else:
                for key, value in updates.items():
                    sessions[session_id][key] = value

        # Run the orchestrator
        orchestrator = PipelineOrchestrator(
            show_progress=False,
            session_callback=session_callback,
        )
        await orchestrator.run(context)

        # Update session with results
        sessions[session_id]["files"] = context.generated_files
        sessions[session_id]["security_issues"] = [
            {
                "severity": i.severity.value,
                "rule_id": i.rule_id,
                "description": i.description,
                "file_path": i.file_path,
                "line_number": i.line_number,
                "scanner": i.scanner,
            }
            for i in context.security_issues
        ]
        sessions[session_id]["validation_errors"] = [
            {
                "type": e.error_type,
                "message": e.message,
                "file_path": e.file_path,
                "line_number": e.line_number,
            }
            for e in context.validation_errors
        ]
        sessions[session_id]["cost_estimate"] = {
            "monthly": context.total_monthly_cost,
            "yearly": context.total_yearly_cost,
            "breakdown": [
                {
                    "resource": c.resource_name,
                    "type": c.resource_type,
                    "monthly": c.monthly_cost,
                    "yearly": c.yearly_cost,
                }
                for c in context.cost_breakdown
            ],
        } if context.cost_estimated else None
        sessions[session_id]["pipeline_summary"] = context.to_dict()

        if context.pipeline_failed:
            sessions[session_id]["status"] = "error"
            sessions[session_id]["error"] = context.failure_reason
        elif context.security_issues and not context.security_passed:
            sessions[session_id]["status"] = "completed_with_warnings"
        else:
            sessions[session_id]["status"] = "completed"

        duration = time.time() - start_time
        sessions[session_id]["duration"] = duration

        log_generate(
            "Image-based generation completed",
            session_id=session_id,
            provider=request.provider,
            duration=duration,
            files=len(sessions[session_id].get("files", {})),
        )

    except Exception as e:
        duration = time.time() - start_time
        sessions[session_id]["status"] = "error"
        sessions[session_id]["error"] = str(e)

        log_error(
            "Image-based generation failed",
            str(e),
            session_id=session_id,
            duration=duration,
        )


async def run_generation(
    session_id: str,
    request: GenerateRequest,
    output_dir: Path,
    username: str,
):
    """Run the actual generation using the multi-agent pipeline."""
    start_time = time.time()

    try:
        sessions[session_id]["status"] = "running"
        log_agent("Agent pipeline started", session_id=session_id)

        # Import from terragen core
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

        from terragen.config import PROVIDER_REGIONS

        # Get region
        region = request.region
        if not region:
            region = PROVIDER_REGIONS.get(request.provider, {}).get(
                "default", "us-east-1"
            )

        # Build clarifications from request options
        clarifications = request.clarifications or {}
        if request.options:
            clarifications.update(request.options)

        # Add backend info to clarifications if specified
        backend = request.backend or "local"
        backend_config = None
        if backend != "local":
            clarifications["backend"] = backend
            clarifications["backend_instruction"] = f"Configure Terraform to use {backend} backend for state storage"
            # Use full backend config if provided, otherwise just type
            if request.backendConfig:
                backend_config = request.backendConfig.model_dump(exclude_none=True)
            else:
                backend_config = {"type": backend}

        if request.use_pipeline:
            # Use the multi-agent pipeline
            from terragen.agents.context import PipelineContext
            from terragen.agents.orchestrator import PipelineOrchestrator

            # Create pipeline context
            context = PipelineContext(
                user_prompt=request.prompt,
                provider=request.provider,
                region=region,
                output_dir=output_dir,
                skip_clarify=request.skip_clarify,
                skip_cost=request.skip_cost,
                skip_security=request.skip_security,
                max_security_fix_attempts=request.max_security_fixes,
                chat_mode=False,
                backend_config=backend_config,
            )

            # Pre-populate clarifications if provided
            if clarifications:
                context.clarifications = clarifications

            # Callback to update session state from orchestrator
            def session_callback(updates: dict):
                if "log" in updates:
                    # Append log entry
                    if "logs" not in sessions[session_id]:
                        sessions[session_id]["logs"] = []
                    sessions[session_id]["logs"].append(updates["log"])
                elif "completed_agent" in updates:
                    # Track completed agents
                    if "completed_agents" not in sessions[session_id]:
                        sessions[session_id]["completed_agents"] = []
                    agent_name = updates["completed_agent"]
                    if agent_name not in sessions[session_id]["completed_agents"]:
                        sessions[session_id]["completed_agents"].append(agent_name)
                    # Remove from failed_agents if it was there (succeeded on retry)
                    if "failed_agents" in sessions[session_id] and agent_name in sessions[session_id]["failed_agents"]:
                        sessions[session_id]["failed_agents"].remove(agent_name)
                elif "skipped_agent" in updates:
                    # Track skipped agents
                    if "skipped_agents" not in sessions[session_id]:
                        sessions[session_id]["skipped_agents"] = []
                    sessions[session_id]["skipped_agents"].append(updates["skipped_agent"])
                elif "failed_agent" in updates:
                    # Track failed agents (only if not already completed)
                    if "failed_agents" not in sessions[session_id]:
                        sessions[session_id]["failed_agents"] = []
                    agent_name = updates["failed_agent"]
                    # Don't add if already completed (edge case)
                    if "completed_agents" not in sessions[session_id] or agent_name not in sessions[session_id]["completed_agents"]:
                        if agent_name not in sessions[session_id]["failed_agents"]:
                            sessions[session_id]["failed_agents"].append(agent_name)
                else:
                    # Update other session fields
                    for key, value in updates.items():
                        sessions[session_id][key] = value

            # Run the orchestrator with callback
            orchestrator = PipelineOrchestrator(
                show_progress=False,
                session_callback=session_callback,
            )
            await orchestrator.run(context)

            # Update session with results
            sessions[session_id]["files"] = context.generated_files
            sessions[session_id]["security_issues"] = [
                {
                    "severity": i.severity.value,
                    "rule_id": i.rule_id,
                    "description": i.description,
                    "file_path": i.file_path,
                    "line_number": i.line_number,
                    "scanner": i.scanner,
                }
                for i in context.security_issues
            ]
            sessions[session_id]["validation_errors"] = [
                {
                    "type": e.error_type,
                    "message": e.message,
                    "file_path": e.file_path,
                    "line_number": e.line_number,
                }
                for e in context.validation_errors
            ]
            sessions[session_id]["cost_estimate"] = {
                "monthly": context.total_monthly_cost,
                "yearly": context.total_yearly_cost,
                "breakdown": [
                    {
                        "resource": c.resource_name,
                        "type": c.resource_type,
                        "monthly": c.monthly_cost,
                        "yearly": c.yearly_cost,
                    }
                    for c in context.cost_breakdown
                ],
            } if context.cost_estimated else None
            sessions[session_id]["pipeline_summary"] = context.to_dict()

            if context.pipeline_failed:
                sessions[session_id]["status"] = "error"
                sessions[session_id]["error"] = context.failure_reason
            elif context.security_issues and not context.security_passed:
                # Completed but with unresolved security issues
                sessions[session_id]["status"] = "completed_with_warnings"
            else:
                sessions[session_id]["status"] = "completed"

        else:
            # Use legacy single-agent generator
            from terragen.generator import generate_terraform

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: generate_terraform(
                    prompt=request.prompt,
                    output_dir=output_dir,
                    provider=request.provider,
                    region=region,
                    clarifications=clarifications if clarifications else None,
                    chat_mode=False,
                ),
            )

            # Read generated files (all relevant file types)
            files = {}
            file_patterns = ["*.tf", "*.tfvars", "*.md", "*.json", "*.yaml", "*.yml"]
            for pattern in file_patterns:
                for file_path in output_dir.glob(pattern):
                    if file_path.is_file():
                        files[file_path.name] = file_path.read_text()

            sessions[session_id]["status"] = "completed"
            sessions[session_id]["files"] = files

        duration = time.time() - start_time
        sessions[session_id]["duration"] = duration

        log_generate(
            "Generation completed",
            session_id=session_id,
            provider=request.provider,
            duration=duration,
            files=len(sessions[session_id].get("files", {})),
            use_pipeline=request.use_pipeline,
        )

    except Exception as e:
        duration = time.time() - start_time
        sessions[session_id]["status"] = "error"
        sessions[session_id]["error"] = str(e)

        log_error(
            "Generation failed",
            str(e),
            session_id=session_id,
            duration=duration,
        )


@router.get("/{session_id}", response_model=GenerateResponse)
async def get_generation_status(
    session_id: str,
    user: User = Depends(get_current_user),
):
    """Get generation status and results."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]

    if session["user"] != user.username:
        raise HTTPException(status_code=403, detail="Not authorized")

    return GenerateResponse(
        session_id=session_id,
        status=session["status"],
        files=session.get("files"),
        cost_estimate=session.get("cost_estimate"),
        security_issues=session.get("security_issues"),
        validation_errors=session.get("validation_errors"),
        plan=session.get("plan"),
        pipeline_summary=session.get("pipeline_summary"),
        error=session.get("error"),
    )


@router.get("/{session_id}/stream")
async def stream_generation(
    session_id: str,
    token: str = None,
):
    """Stream generation progress via SSE.

    Note: Uses token query param because EventSource doesn't support headers.
    """
    user = get_user_from_query_token(token)
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]

    if session["user"] != user.username:
        raise HTTPException(status_code=403, detail="Not authorized")

    async def event_generator():
        last_log_index = 0
        while True:
            status = sessions[session_id]["status"]

            # Get new logs since last check
            all_logs = sessions[session_id].get("logs", [])
            new_logs = all_logs[last_log_index:] if last_log_index < len(all_logs) else []
            last_log_index = len(all_logs)

            data = {
                "status": status,
                "current_agent": sessions[session_id].get("current_agent"),
                "completed_agents": sessions[session_id].get("completed_agents", []),
                "skipped_agents": sessions[session_id].get("skipped_agents", []),
                "failed_agents": sessions[session_id].get("failed_agents", []),
                "files": sessions[session_id].get("files"),
                "security_issues": sessions[session_id].get("security_issues"),
                "validation_errors": sessions[session_id].get("validation_errors"),
                "cost_estimate": sessions[session_id].get("cost_estimate"),
                "error": sessions[session_id].get("error"),
                "fix_attempt": sessions[session_id].get("fix_attempt"),
                "max_fix_attempts": sessions[session_id].get("max_fix_attempts"),
                "logs": new_logs,
            }

            yield f"data: {json.dumps(data)}\n\n"

            if status in ["completed", "completed_with_warnings", "error"]:
                break

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )


@router.put("/{session_id}/files")
async def update_session_files(
    session_id: str,
    request: UpdateFilesRequest,
    user: User = Depends(get_current_user),
):
    """Update files in an existing session."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]

    if session["user"] != user.username:
        raise HTTPException(status_code=403, detail="Not authorized")

    if session["status"] not in ["completed", "completed_with_warnings"]:
        raise HTTPException(status_code=400, detail="Can only update files in completed sessions")

    # Update files in session
    sessions[session_id]["files"] = request.files

    # Also write files to disk
    output_dir = Path(session["output_dir"])
    for filename, content in request.files.items():
        file_path = output_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

    log_generate("Files updated", session_id=session_id)

    return {"status": "success", "message": f"Updated {len(request.files)} files"}


@router.post("/{session_id}/download")
async def download_files(
    session_id: str,
    user: User = Depends(get_current_user),
):
    """Download generated files as zip."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]

    if session["user"] != user.username:
        raise HTTPException(status_code=403, detail="Not authorized")

    if session["status"] != "completed":
        raise HTTPException(status_code=400, detail="Generation not complete")

    output_dir = Path(session["output_dir"])

    # Create zip file
    zip_path = shutil.make_archive(
        str(output_dir.parent / f"terraform_{session_id[:8]}"),
        "zip",
        output_dir,
    )

    log_generate("Files downloaded", session_id=session_id)

    def iterfile():
        with open(zip_path, "rb") as f:
            yield from f
        Path(zip_path).unlink()

    return StreamingResponse(
        iterfile(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=terraform_{session_id[:8]}.zip"
        },
    )
