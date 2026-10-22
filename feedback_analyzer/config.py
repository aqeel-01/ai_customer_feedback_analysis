"""
config.py
=========
Loads and validates application configuration from environment variables and .env.
Exposes a strongly-typed Config dataclass.
Never logs or prints secrets.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load .env file if present in the current working directory or project root
load_dotenv()


@dataclass(frozen=True)
class Config:
    """Application configuration settings."""

    groq_api_key: str
    model_name: str = "llama-3.1-8b-instant"
    db_path: str = "output/feedback.db"
    output_dir: str = "output"
    log_level: str = "INFO"
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 3

    @classmethod
    def from_env(cls) -> Config:
        """Construct Config from environment variables with sensible defaults."""
        return cls(
            groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
            model_name=os.getenv("MODEL_NAME", "llama-3.1-8b-instant").strip(),
            db_path=os.getenv("DB_PATH", "output/feedback.db").strip(),
            output_dir=os.getenv("OUTPUT_DIR", "output").strip(),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
            llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "30")),
            llm_max_retries=int(os.getenv("LLM_MAX_RETRIES", "3")),
        )

    def validate_for_llm(self) -> None:
        """
        Validate that required credentials for LLM calls are present.
        Raises ValueError if GROQ_API_KEY is missing or looks like a placeholder.
        """
        if not self.groq_api_key or self.groq_api_key == "your_groq_api_key_here":
            raise ValueError(
                "GROQ_API_KEY is not set or is still the placeholder value. "
                "Please set GROQ_API_KEY in your environment or in a .env file."
            )


# Default singleton config instance
_config: Config | None = None


def get_config() -> Config:
    """Return the global cached Config instance, or create it from env."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config
