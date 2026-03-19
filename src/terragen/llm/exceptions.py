"""
Custom exceptions for LLM providers.
"""


class LLMError(Exception):
    """Base exception for LLM errors."""
    def __init__(self, message: str, provider: str = "unknown"):
        self.provider = provider
        super().__init__(f"[{provider}] {message}")


class RateLimitError(LLMError):
    """Raised when rate limit is exceeded. Retryable with backoff."""
    pass


class APIError(LLMError):
    """Raised for general API errors. May be retryable."""
    def __init__(self, message: str, provider: str = "unknown", status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message, provider)


class AuthenticationError(LLMError):
    """Raised when authentication fails. Not retryable - skip provider."""
    pass


class TimeoutError(LLMError):
    """Raised when request times out. Retryable."""
    pass


class NoAvailableProviderError(LLMError):
    """Raised when all providers have failed."""
    def __init__(self, errors: list[tuple[str, Exception]], unavailable: list[str] | None = None):
        self.errors = errors
        self.unavailable = unavailable or []

        parts = []
        if errors:
            error_summary = "; ".join(f"{p}: {e}" for p, e in errors)
            parts.append(f"Errors: {error_summary}")
        if self.unavailable:
            env_vars = {"xai": "XAI_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
            missing = [f"{p} ({env_vars.get(p, p.upper() + '_API_KEY')})" for p in self.unavailable]
            parts.append(f"Unavailable (no API key): {', '.join(missing)}")

        message = " | ".join(parts) if parts else "No providers configured"
        super().__init__(message, "unified")
