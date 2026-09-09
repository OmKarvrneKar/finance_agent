"""
Application configuration — environment validation and defaults.

Required environment variables are validated at startup.
Secret values are NEVER exposed in error messages or logs.
"""

import os
import sys
import logging

logger = logging.getLogger(__name__)


class Config:
    """Central configuration validated at startup."""

    # --- Required secrets (must be set) ---
    JWT_SECRET_KEY: str = ""

    # --- Optional with defaults ---
    DATABASE_URL: str = "sqlite:///finance.db"
    UPLOAD_DIR: str = "uploads"
    ENVIRONMENT: str = "development"

    # --- Optional secrets (not required, but validated if set) ---
    OPENROUTER_API_KEY: str = ""

    _validated = False

    @classmethod
    def validate(cls) -> None:
        """
        Validate all required environment variables.
        Exits the process if any required variable is missing.
        Secret values are NEVER logged or included in error messages.
        """
        if cls._validated:
            return

        errors = []

        # JWT_SECRET_KEY — required
        jwt_secret = os.getenv("JWT_SECRET_KEY", "")
        if not jwt_secret:
            errors.append("JWT_SECRET_KEY")
        cls.JWT_SECRET_KEY = jwt_secret

        # DATABASE_URL — optional, defaults to sqlite
        cls.DATABASE_URL = os.getenv("DATABASE_URL", cls.DATABASE_URL)

        # UPLOAD_DIR — optional, defaults to "uploads"
        cls.UPLOAD_DIR = os.getenv("UPLOAD_DIR", cls.UPLOAD_DIR)

        # ENVIRONMENT — optional
        cls.ENVIRONMENT = os.getenv("ENVIRONMENT", cls.ENVIRONMENT).lower()

        # OPENROUTER_API_KEY — optional but warned if missing
        cls.OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
        if not cls.OPENROUTER_API_KEY:
            logger.warning("OPENROUTER_API_KEY is not set. AI features will be unavailable.")

        if errors:
            missing = ", ".join(errors)
            logger.critical(
                f"FATAL: Required environment variable(s) not set: {missing}. "
                "Application cannot start. See .env.example for reference."
            )
            sys.exit(1)

        cls._validated = True
        logger.info(f"Configuration validated. Environment: {cls.ENVIRONMENT}")

    @classmethod
    def get_db_url(cls) -> str:
        """Return the database URL, using the same value that the app uses."""
        return cls.DATABASE_URL

    @classmethod
    def get_upload_dir(cls) -> str:
        """Return the upload directory path."""
        return cls.UPLOAD_DIR


def validate_startup() -> None:
    """Called once at application startup to validate configuration."""
    Config.validate()
