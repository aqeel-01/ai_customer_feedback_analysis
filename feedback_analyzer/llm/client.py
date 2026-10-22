"""
llm/client.py
=============
Provider-specific LLM client wrapper for Groq.
Handles authentication, timeout, retries with exponential backoff, and exception mapping.
Never exposes or logs API secrets.
"""

from __future__ import annotations

import logging
from typing import Any

import groq
from groq import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from feedback_analyzer.config import Config, get_config

logger = logging.getLogger(__name__)


# --- Domain Exceptions ---


class LLMError(Exception):
    """Base exception for all LLM integration failures."""


class LLMAuthenticationError(LLMError):
    """Raised when API authentication fails (e.g., invalid or missing API key)."""


class LLMRateLimitError(LLMError):
    """Raised when API rate limits are exceeded after retries."""


class LLMTimeoutError(LLMError):
    """Raised when an API call times out after retries."""


class LLMResponseError(LLMError):
    """Raised when the LLM returns an empty, corrupted, or unparsable response."""


# Transient exceptions eligible for bounded retry
RETRYABLE_EXCEPTIONS = (
    RateLimitError,
    APITimeoutError,
    APIConnectionError,
    InternalServerError,
)


class GroqClient:
    """
    Service client for interacting with Groq's LLM API.
    Enforces timeout, bounded retries on transient errors, and masks secrets in logs.
    """

    def __init__(self, config: Config | None = None, client: Any | None = None) -> None:
        self.config = config or get_config()
        self._raw_client = client

    def _get_client(self) -> groq.Groq:
        """Lazy-initialize the Groq SDK client."""
        if self._raw_client is not None:
            return self._raw_client

        # Validate configuration before attempting to connect
        self.config.validate_for_llm()

        self._raw_client = groq.Groq(
            api_key=self.config.groq_api_key,
            timeout=self.config.llm_timeout_seconds,
        )
        return self._raw_client

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """
        Execute a chat completion request with configured retries and error mapping.
        Never logs the API key or raw credentials.
        """
        # Validate configuration upfront if client has not been pre-injected
        if self._raw_client is None:
            self.config.validate_for_llm()

        max_retries = max(1, self.config.llm_max_retries)

        @retry(
            reraise=True,
            stop=stop_after_attempt(max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        )
        def _execute_with_retry() -> str:
            client = self._get_client()
            logger.debug(
                "Sending request to model %s (timeout=%ss)",
                self.config.model_name,
                self.config.llm_timeout_seconds,
            )

            response = client.chat.completions.create(
                model=self.config.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )

            choices = getattr(response, "choices", None)
            if not choices:
                raise LLMResponseError("LLM response contained no choices")

            first_choice = choices[0]
            message = getattr(first_choice, "message", None)
            content = getattr(message, "content", None)

            if not content or not content.strip():
                raise LLMResponseError("LLM response content was empty")

            return content.strip()

        try:
            return _execute_with_retry()
        except ValueError:
            raise
        except AuthenticationError as e:
            logger.error("Authentication failed with Groq API. Please verify GROQ_API_KEY.")
            raise LLMAuthenticationError("Authentication failed: invalid or expired API key") from e
        except RateLimitError as e:
            logger.error("Rate limit exceeded for model %s after retries.", self.config.model_name)
            raise LLMRateLimitError("Rate limit exceeded after maximum retries") from e
        except APITimeoutError as e:
            logger.error("LLM request timed out after %s seconds.", self.config.llm_timeout_seconds)
            raise LLMTimeoutError("Request timed out after maximum retries") from e
        except (APIConnectionError, InternalServerError) as e:
            logger.error("Temporary Groq API communication failure: %s", type(e).__name__)
            raise LLMError(f"Temporary API failure after retries: {type(e).__name__}") from e
        except BadRequestError as e:
            logger.error("Bad request sent to Groq API: %s", e)
            raise LLMError(f"Bad request error: {e}") from e
        except LLMResponseError:
            raise
        except Exception as e:
            logger.error("Unexpected error during LLM invocation: %s", type(e).__name__)
            raise LLMError(f"Unexpected error calling LLM: {e}") from e
