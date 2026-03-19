"""Logging configuration for TerraGen API."""

import logging
import sys
from datetime import datetime

# Create formatter
class TerraGenFormatter(logging.Formatter):
    """Custom formatter with colors and structured output."""

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record):
        # Add color
        color = self.COLORS.get(record.levelname, self.RESET)

        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")

        # Build message
        msg = f"{color}{timestamp} [{record.levelname:^8}]{self.RESET} {record.getMessage()}"

        # Add extra fields if present
        if hasattr(record, "user"):
            msg += f" | user={record.user}"
        if hasattr(record, "session_id"):
            msg += f" | session={record.session_id[:8]}"
        if hasattr(record, "provider"):
            msg += f" | provider={record.provider}"
        if hasattr(record, "duration"):
            msg += f" | duration={record.duration:.2f}s"

        return msg


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Set up logging for the application."""
    # Create logger
    logger = logging.getLogger("terragen")
    logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    logger.handlers.clear()

    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(TerraGenFormatter())
    logger.addHandler(handler)

    # Suppress noisy loggers
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    return logger


# Global logger instance
logger = setup_logging()


def log_auth(action: str, user: str = None, success: bool = True):
    """Log authentication events."""
    extra = {"user": user} if user else {}
    if success:
        logger.info(f"Auth: {action}", extra=extra)
    else:
        logger.warning(f"Auth failed: {action}", extra=extra)


def log_generate(action: str, session_id: str, provider: str = None, **kwargs):
    """Log generation events."""
    extra = {"session_id": session_id}
    if provider:
        extra["provider"] = provider
    extra.update(kwargs)
    logger.info(f"Generate: {action}", extra=extra)


def log_agent(action: str, session_id: str, step: int = None, tool: str = None):
    """Log agent loop events."""
    msg = f"Agent: {action}"
    if step is not None:
        msg += f" (step {step})"
    if tool:
        msg += f" [{tool}]"
    logger.info(msg, extra={"session_id": session_id})


def log_modify(action: str, session_id: str, repo: str = None, **kwargs):
    """Log modification events."""
    extra = {"session_id": session_id}
    if repo:
        msg = f"Modify: {action} | repo={repo}"
    else:
        msg = f"Modify: {action}"
    logger.info(msg, extra=extra)


def log_validate(action: str, valid: bool = None, errors: int = 0):
    """Log validation events."""
    if valid is not None:
        status = "passed" if valid else "failed"
        logger.info(f"Validate: {action} | {status} | errors={errors}")
    else:
        logger.info(f"Validate: {action}")


def log_error(action: str, error: str, **kwargs):
    """Log errors."""
    logger.error(f"{action}: {error}", extra=kwargs)
