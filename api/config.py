"""API configuration."""

from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
from typing import Optional

# Root .env file path
ROOT_DIR = Path(__file__).parent.parent
ENV_FILE = ROOT_DIR / ".env"


class Settings(BaseSettings):
    """Application settings."""

    # App
    app_name: str = "TerraGen API"
    debug: bool = False

    # GitHub OAuth
    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = "http://localhost:3000/auth/callback/github"
    github_url: str = "https://github.com"  # For GitHub Enterprise
    github_api_url: str = "https://api.github.com"

    # GitLab OAuth
    gitlab_client_id: str = ""
    gitlab_client_secret: str = ""
    gitlab_redirect_uri: str = "http://localhost:3000/auth/callback/gitlab"
    gitlab_url: str = "https://gitlab.com"  # For self-hosted GitLab

    # Bitbucket OAuth
    bitbucket_client_id: str = ""
    bitbucket_client_secret: str = ""
    bitbucket_redirect_uri: str = "http://localhost:3000/auth/callback/bitbucket"
    bitbucket_url: str = "https://bitbucket.org"  # For Bitbucket Server
    bitbucket_api_url: str = "https://api.bitbucket.org/2.0"

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24

    # API Keys
    anthropic_api_key: str = ""
    xai_api_key: str = ""
    openai_api_key: str = ""
    infracost_api_key: str = ""

    # CORS - comma-separated list of origins
    # e.g., CORS_ORIGINS=http://localhost:3000,https://app.deos.dev
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    class Config:
        env_file = str(ENV_FILE)
        env_file_encoding = "utf-8"
        extra = "ignore"

    def get_enabled_providers(self) -> list[str]:
        """Get list of enabled git providers."""
        providers = []
        if self.github_client_id:
            providers.append("github")
        if self.gitlab_client_id:
            providers.append("gitlab")
        if self.bitbucket_client_id:
            providers.append("bitbucket")
        return providers


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings."""
    return Settings()
