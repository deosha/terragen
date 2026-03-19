"""Multi-provider OAuth and JWT authentication."""

import httpx
from datetime import datetime, timedelta
from typing import Optional, Literal
from jose import jwt, JWTError
from cryptography.fernet import Fernet
from pydantic import BaseModel
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .config import get_settings

security = HTTPBearer()

GitProvider = Literal["github", "gitlab", "bitbucket"]


class GitUser(BaseModel):
    """Git provider user info."""

    id: int | str
    username: str
    email: Optional[str] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    provider: GitProvider


class TokenData(BaseModel):
    """JWT token payload."""

    sub: str  # Username
    provider: GitProvider
    user_id: int | str
    email: Optional[str] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    git_token: str  # Encrypted git access token
    exp: datetime


class User(BaseModel):
    """Authenticated user."""

    username: str
    provider: GitProvider
    user_id: int | str
    email: Optional[str] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    git_token: str  # Decrypted token for API calls


def get_encryption_key() -> bytes:
    """Get or generate encryption key from JWT secret."""
    settings = get_settings()
    import hashlib
    import base64

    key = hashlib.sha256(settings.jwt_secret.encode()).digest()
    return base64.urlsafe_b64encode(key)


def encrypt_token(token: str) -> str:
    """Encrypt git token for storage in JWT."""
    f = Fernet(get_encryption_key())
    return f.encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    """Decrypt git token from JWT."""
    f = Fernet(get_encryption_key())
    return f.decrypt(encrypted.encode()).decode()


# =============================================================================
# GitHub
# =============================================================================


async def github_exchange_code(code: str) -> str:
    """Exchange GitHub OAuth code for access token."""
    settings = get_settings()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.github_url}/login/oauth/access_token",
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_redirect_uri,
            },
            headers={"Accept": "application/json"},
        )

        data = response.json()

        if "error" in data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=data.get("error_description", data["error"]),
            )

        return data["access_token"]


async def github_get_user(access_token: str) -> GitUser:
    """Get GitHub user info."""
    settings = get_settings()

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{settings.github_api_url}/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid GitHub token",
            )

        data = response.json()

        # Get primary email if not public
        email = data.get("email")
        if not email:
            email_response = await client.get(
                f"{settings.github_api_url}/user/emails",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            if email_response.status_code == 200:
                emails = email_response.json()
                primary = next((e for e in emails if e.get("primary")), None)
                if primary:
                    email = primary["email"]

        return GitUser(
            id=data["id"],
            username=data["login"],
            email=email,
            name=data.get("name"),
            avatar_url=data.get("avatar_url"),
            provider="github",
        )


# =============================================================================
# GitLab
# =============================================================================


async def gitlab_exchange_code(code: str) -> str:
    """Exchange GitLab OAuth code for access token."""
    settings = get_settings()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.gitlab_url}/oauth/token",
            data={
                "client_id": settings.gitlab_client_id,
                "client_secret": settings.gitlab_client_secret,
                "code": code,
                "redirect_uri": settings.gitlab_redirect_uri,
                "grant_type": "authorization_code",
            },
        )

        data = response.json()

        if "error" in data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=data.get("error_description", data["error"]),
            )

        return data["access_token"]


async def gitlab_get_user(access_token: str) -> GitUser:
    """Get GitLab user info."""
    settings = get_settings()

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{settings.gitlab_url}/api/v4/user",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid GitLab token",
            )

        data = response.json()

        return GitUser(
            id=data["id"],
            username=data["username"],
            email=data.get("email"),
            name=data.get("name"),
            avatar_url=data.get("avatar_url"),
            provider="gitlab",
        )


# =============================================================================
# Bitbucket
# =============================================================================


async def bitbucket_exchange_code(code: str) -> str:
    """Exchange Bitbucket OAuth code for access token."""
    settings = get_settings()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://bitbucket.org/site/oauth2/access_token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.bitbucket_redirect_uri,
            },
            auth=(settings.bitbucket_client_id, settings.bitbucket_client_secret),
        )

        data = response.json()

        if "error" in data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=data.get("error_description", data["error"]),
            )

        return data["access_token"]


async def bitbucket_get_user(access_token: str) -> GitUser:
    """Get Bitbucket user info."""
    settings = get_settings()

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{settings.bitbucket_api_url}/user",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Bitbucket token",
            )

        data = response.json()

        # Get email from separate endpoint
        email = None
        email_response = await client.get(
            f"{settings.bitbucket_api_url}/user/emails",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if email_response.status_code == 200:
            emails = email_response.json().get("values", [])
            primary = next((e for e in emails if e.get("is_primary")), None)
            if primary:
                email = primary["email"]

        return GitUser(
            id=data["uuid"],
            username=data["username"],
            email=email,
            name=data.get("display_name"),
            avatar_url=data.get("links", {}).get("avatar", {}).get("href"),
            provider="bitbucket",
        )


# =============================================================================
# Unified Functions
# =============================================================================


async def exchange_code_for_token(code: str, provider: GitProvider) -> str:
    """Exchange OAuth code for access token."""
    if provider == "github":
        return await github_exchange_code(code)
    elif provider == "gitlab":
        return await gitlab_exchange_code(code)
    elif provider == "bitbucket":
        return await bitbucket_exchange_code(code)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider: {provider}",
        )


async def get_git_user(access_token: str, provider: GitProvider) -> GitUser:
    """Get user info from git provider."""
    if provider == "github":
        return await github_get_user(access_token)
    elif provider == "gitlab":
        return await gitlab_get_user(access_token)
    elif provider == "bitbucket":
        return await bitbucket_get_user(access_token)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider: {provider}",
        )


def create_jwt_token(user: GitUser, git_token: str) -> str:
    """Create JWT token with user info and encrypted git token."""
    settings = get_settings()

    expires = datetime.utcnow() + timedelta(hours=settings.jwt_expiration_hours)

    token_data = TokenData(
        sub=user.username,
        provider=user.provider,
        user_id=user.id,
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url,
        git_token=encrypt_token(git_token),
        exp=expires,
    )

    return jwt.encode(
        token_data.model_dump(),
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """Get current authenticated user from JWT token."""
    return decode_jwt_token(credentials.credentials)


def decode_jwt_token(token: str) -> User:
    """Decode and validate a JWT token, returning the User."""
    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )

        username = payload.get("sub")
        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

        return User(
            username=username,
            provider=payload["provider"],
            user_id=payload["user_id"],
            email=payload.get("email"),
            name=payload.get("name"),
            avatar_url=payload.get("avatar_url"),
            git_token=decrypt_token(payload["git_token"]),
        )

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


def get_user_from_query_token(token: Optional[str] = None) -> User:
    """Get user from token passed as query parameter (for SSE endpoints)."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token required",
        )
    return decode_jwt_token(token)


def get_clone_url(user: User, owner: str, repo: str) -> str:
    """Get authenticated clone URL for a repository."""
    settings = get_settings()

    if user.provider == "github":
        return f"https://{user.git_token}@{settings.github_url.replace('https://', '')}/{owner}/{repo}.git"
    elif user.provider == "gitlab":
        return f"https://oauth2:{user.git_token}@{settings.gitlab_url.replace('https://', '')}/{owner}/{repo}.git"
    elif user.provider == "bitbucket":
        return f"https://x-token-auth:{user.git_token}@{settings.bitbucket_url.replace('https://', '')}/{owner}/{repo}.git"
    else:
        raise ValueError(f"Unknown provider: {user.provider}")
