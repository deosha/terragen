"""Authentication routes for multiple git providers."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Literal

from ..config import get_settings
from ..auth import (
    exchange_code_for_token,
    get_git_user,
    create_jwt_token,
    GitProvider,
)
from ..logging_config import log_auth, log_error

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginResponse(BaseModel):
    """Login URL response."""

    url: str
    provider: str


class ProvidersResponse(BaseModel):
    """Available providers response."""

    providers: list[dict]


class CallbackRequest(BaseModel):
    """OAuth callback request."""

    code: str
    provider: GitProvider


class TokenResponse(BaseModel):
    """JWT token response."""

    access_token: str
    token_type: str = "bearer"
    user: dict


@router.get("/providers", response_model=ProvidersResponse)
async def get_providers():
    """Get available OAuth providers."""
    settings = get_settings()
    providers = []

    if settings.github_client_id:
        providers.append(
            {
                "id": "github",
                "name": "GitHub",
                "icon": "github",
            }
        )

    if settings.gitlab_client_id:
        providers.append(
            {
                "id": "gitlab",
                "name": "GitLab",
                "icon": "gitlab",
            }
        )

    if settings.bitbucket_client_id:
        providers.append(
            {
                "id": "bitbucket",
                "name": "Bitbucket",
                "icon": "bitbucket",
            }
        )

    return ProvidersResponse(providers=providers)


@router.get("/login/{provider}", response_model=LoginResponse)
async def login(provider: GitProvider):
    """Get OAuth login URL for a specific provider."""
    settings = get_settings()

    if provider == "github":
        if not settings.github_client_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub OAuth not configured",
            )
        url = (
            f"{settings.github_url}/login/oauth/authorize"
            f"?client_id={settings.github_client_id}"
            f"&redirect_uri={settings.github_redirect_uri}"
            f"&scope=repo user:email"
        )

    elif provider == "gitlab":
        if not settings.gitlab_client_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitLab OAuth not configured",
            )
        url = (
            f"{settings.gitlab_url}/oauth/authorize"
            f"?client_id={settings.gitlab_client_id}"
            f"&redirect_uri={settings.gitlab_redirect_uri}"
            f"&response_type=code"
            f"&scope=api read_user read_repository write_repository"
        )

    elif provider == "bitbucket":
        if not settings.bitbucket_client_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bitbucket OAuth not configured",
            )
        url = (
            f"https://bitbucket.org/site/oauth2/authorize"
            f"?client_id={settings.bitbucket_client_id}"
            f"&redirect_uri={settings.bitbucket_redirect_uri}"
            f"&response_type=code"
            f"&scope=repository:write pullrequest:write account"
        )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider: {provider}",
        )

    log_auth(f"Login URL generated for {provider}")
    return LoginResponse(url=url, provider=provider)


@router.post("/callback")
async def callback(request: CallbackRequest):
    """Handle OAuth callback from any provider."""
    try:
        # Exchange code for token
        git_token = await exchange_code_for_token(request.code, request.provider)

        # Get user info
        git_user = await get_git_user(git_token, request.provider)
        log_auth(f"{request.provider} user fetched", user=git_user.username)

        # Create JWT
        jwt_token = create_jwt_token(git_user, git_token)
        log_auth(f"Login successful via {request.provider}", user=git_user.username)

        return {
            "access_token": jwt_token,
            "token_type": "bearer",
            "user": {
                "username": git_user.username,
                "email": git_user.email,
                "name": git_user.name,
                "avatar_url": git_user.avatar_url,
                "provider": git_user.provider,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Auth callback ({request.provider})", str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


@router.get("/me")
async def me(user=None):
    """Get current user info."""
    return {
        "username": user.username if user else None,
        "email": user.email if user else None,
        "name": user.name if user else None,
        "avatar_url": user.avatar_url if user else None,
        "provider": user.provider if user else None,
    }
