"""Modify existing infrastructure routes."""

import tempfile
import time
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
import asyncio
import httpx
import uuid

from ..auth import get_current_user, User, get_clone_url
from ..config import get_settings
from ..logging_config import log_modify, log_agent, log_error

router = APIRouter(prefix="/modify", tags=["modify"])


class RepoInfo(BaseModel):
    """Repository information."""

    owner: str
    repo: str
    branch: str = "main"
    path: str = "."  # Path to terraform files within repo


class ModifyRequest(BaseModel):
    """Modify infrastructure request."""

    prompt: str
    repo: RepoInfo
    create_pr: bool = True


class ModifyResponse(BaseModel):
    """Modify response."""

    session_id: str
    status: str
    branch: Optional[str] = None
    pr_url: Optional[str] = None
    changes: Optional[dict] = None
    plan: Optional[str] = None


# In-memory session storage
modify_sessions: dict = {}


async def clone_repo(
    user: User,
    repo: RepoInfo,
    target_dir: Path,
) -> None:
    """Clone a git repository (supports GitHub, GitLab, Bitbucket)."""
    clone_url = get_clone_url(user, repo.owner, repo.repo)

    process = await asyncio.create_subprocess_exec(
        "git",
        "clone",
        "--branch",
        repo.branch,
        "--depth",
        "1",
        clone_url,
        str(target_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    _, stderr = await process.communicate()

    if process.returncode != 0:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to clone repository: {stderr.decode()}",
        )


async def create_branch(
    target_dir: Path,
    branch_name: str,
) -> None:
    """Create and checkout a new branch."""
    process = await asyncio.create_subprocess_exec(
        "git",
        "checkout",
        "-b",
        branch_name,
        cwd=str(target_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    await process.communicate()


async def commit_and_push(
    target_dir: Path,
    branch_name: str,
    message: str,
    user: User,
) -> None:
    """Commit changes and push to remote."""
    # Configure git
    await asyncio.create_subprocess_exec(
        "git",
        "config",
        "user.email",
        user.email or f"{user.username}@users.noreply.github.com",
        cwd=str(target_dir),
    )
    await asyncio.create_subprocess_exec(
        "git",
        "config",
        "user.name",
        user.name or user.username,
        cwd=str(target_dir),
    )

    # Add all changes
    await asyncio.create_subprocess_exec(
        "git",
        "add",
        "-A",
        cwd=str(target_dir),
    )

    # Commit
    process = await asyncio.create_subprocess_exec(
        "git",
        "commit",
        "-m",
        message,
        cwd=str(target_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await process.communicate()

    # Push
    process = await asyncio.create_subprocess_exec(
        "git",
        "push",
        "-u",
        "origin",
        branch_name,
        cwd=str(target_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    _, stderr = await process.communicate()

    if process.returncode != 0:
        raise Exception(f"Failed to push: {stderr.decode()}")


async def create_pull_request(
    user: User,
    repo: RepoInfo,
    branch_name: str,
    title: str,
    body: str,
) -> str:
    """Create a pull request on GitHub."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://api.github.com/repos/{repo.owner}/{repo.repo}/pulls",
            headers={
                "Authorization": f"Bearer {user.github_token}",
                "Accept": "application/vnd.github+json",
            },
            json={
                "title": title,
                "body": body,
                "head": branch_name,
                "base": repo.branch,
            },
        )

        if response.status_code != 201:
            raise Exception(f"Failed to create PR: {response.text}")

        return response.json()["html_url"]


@router.post("/", response_model=ModifyResponse)
async def modify(
    request: ModifyRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
):
    """Start infrastructure modification."""
    session_id = str(uuid.uuid4())
    repo_full = f"{request.repo.owner}/{request.repo.repo}"

    modify_sessions[session_id] = {
        "status": "pending",
        "user": user.username,
        "request": request.model_dump(),
        "started_at": time.time(),
    }

    log_modify(
        "Modification started",
        session_id=session_id,
        repo=repo_full,
        user=user.username,
    )

    # Start modification in background
    background_tasks.add_task(
        run_modification,
        session_id,
        request,
        user,
    )

    return ModifyResponse(
        session_id=session_id,
        status="pending",
    )


async def run_modification(
    session_id: str,
    request: ModifyRequest,
    user: User,
):
    """Run the actual modification."""
    start_time = time.time()
    repo_full = f"{request.repo.owner}/{request.repo.repo}"

    try:
        modify_sessions[session_id]["status"] = "cloning"
        log_modify("Cloning repository", session_id=session_id, repo=repo_full)

        # Create temp directory
        work_dir = Path(tempfile.mkdtemp(prefix="terragen_modify_"))
        repo_dir = work_dir / "repo"

        # Clone repository
        await clone_repo(user, request.repo, repo_dir)

        # Create new branch
        branch_name = f"terragen/{int(time.time())}"
        await create_branch(repo_dir, branch_name)
        log_modify(f"Created branch {branch_name}", session_id=session_id)

        modify_sessions[session_id]["status"] = "modifying"
        modify_sessions[session_id]["branch"] = branch_name

        # Get terraform directory
        tf_dir = repo_dir / request.repo.path

        # Import from terragen core
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

        from terragen.modifier import (
            read_terraform_files,
            read_state_file,
            summarize_state,
        )
        from terragen.agent import run_agent
        from terragen.config import MODIFY_SYSTEM_PROMPT

        # Read existing infrastructure
        tf_files = read_terraform_files(tf_dir)
        state = read_state_file(tf_dir)
        state_summary = summarize_state(state)
        log_modify(f"Read {len(tf_files)} terraform files", session_id=session_id)
        log_agent("Agent loop started", session_id=session_id)

        # Build context
        context = f"""
## Current Terraform Files

{chr(10).join(f'### {name}{chr(10)}```hcl{chr(10)}{content}{chr(10)}```' for name, content in tf_files.items())}

## Current State
{state_summary}
"""

        # Run agent loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: run_agent(
                f"{context}\n\n## Requested Change\n{request.prompt}",
                tf_dir,
                system_prompt=MODIFY_SYSTEM_PROMPT,
            ),
        )

        # Read modified files
        modified_files = {}
        for tf_file in tf_dir.glob("*.tf"):
            new_content = tf_file.read_text()
            old_content = tf_files.get(tf_file.name, "")
            if new_content != old_content:
                modified_files[tf_file.name] = {
                    "old": old_content,
                    "new": new_content,
                }

        modify_sessions[session_id]["changes"] = modified_files
        log_modify(f"Modified {len(modified_files)} files", session_id=session_id)

        if request.create_pr and modified_files:
            modify_sessions[session_id]["status"] = "creating_pr"
            log_modify("Creating pull request", session_id=session_id, repo=repo_full)

            # Commit and push
            await commit_and_push(
                repo_dir,
                branch_name,
                f"TerraGen: {request.prompt[:50]}",
                user,
            )

            # Create PR
            pr_url = await create_pull_request(
                user,
                request.repo,
                branch_name,
                f"TerraGen: {request.prompt[:50]}",
                f"""## Changes

This PR was generated by TerraGen based on the following request:

> {request.prompt}

## Modified Files

{chr(10).join(f'- `{name}`' for name in modified_files.keys())}

---
*Generated by [TerraGen](https://github.com/terragen)*
""",
            )

            modify_sessions[session_id]["pr_url"] = pr_url
            log_modify(f"PR created: {pr_url}", session_id=session_id)

        duration = time.time() - start_time
        modify_sessions[session_id]["status"] = "completed"
        modify_sessions[session_id]["duration"] = duration
        log_modify(
            "Modification completed",
            session_id=session_id,
            repo=repo_full,
            duration=duration,
        )

    except Exception as e:
        duration = time.time() - start_time
        modify_sessions[session_id]["status"] = "error"
        modify_sessions[session_id]["error"] = str(e)
        log_error("Modification failed", str(e), session_id=session_id)


@router.get("/{session_id}", response_model=ModifyResponse)
async def get_modification_status(
    session_id: str,
    user: User = Depends(get_current_user),
):
    """Get modification status and results."""
    if session_id not in modify_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = modify_sessions[session_id]

    if session["user"] != user.username:
        raise HTTPException(status_code=403, detail="Not authorized")

    return ModifyResponse(
        session_id=session_id,
        status=session["status"],
        branch=session.get("branch"),
        pr_url=session.get("pr_url"),
        changes=session.get("changes"),
        plan=session.get("plan"),
    )


@router.get("/repos")
async def list_repos(
    user: User = Depends(get_current_user),
):
    """List user's GitHub repositories."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.github.com/user/repos",
            headers={
                "Authorization": f"Bearer {user.github_token}",
                "Accept": "application/vnd.github+json",
            },
            params={
                "sort": "updated",
                "per_page": 100,
            },
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="Failed to fetch repositories",
            )

        repos = response.json()

        # Filter repos that might contain Terraform
        return [
            {
                "owner": repo["owner"]["login"],
                "name": repo["name"],
                "full_name": repo["full_name"],
                "default_branch": repo["default_branch"],
                "private": repo["private"],
            }
            for repo in repos
        ]
