"""TerraGen API - FastAPI application."""

import os
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .auth import get_current_user
from .routes import auth, generate, modify, validate
from .logging_config import logger

app = FastAPI(
    title="TerraGen API",
    description="AI-powered Terraform code generator API",
    version="1.0.0",
)


@app.on_event("startup")
async def startup():
    """Log startup and set environment variables."""
    settings = get_settings()

    # Set ANTHROPIC_API_KEY for the SDK to find
    if settings.anthropic_api_key:
        os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
        logger.info("TerraGen API started with Anthropic API key configured")
    else:
        logger.warning("TerraGen API started WITHOUT Anthropic API key - generation will fail")

# CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(auth.router)
app.include_router(generate.router)
app.include_router(modify.router)
app.include_router(validate.router)


@app.get("/")
async def root():
    """API root."""
    return {
        "name": "TerraGen API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "healthy"}


@app.get("/me")
async def me(user=Depends(get_current_user)):
    """Get current user info."""
    return {
        "username": user.username,
        "email": user.email,
        "name": user.name,
        "avatar_url": user.avatar_url,
    }
