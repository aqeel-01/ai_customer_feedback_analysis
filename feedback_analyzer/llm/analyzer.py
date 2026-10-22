"""
llm/analyzer.py
===============
Builds the prompt from a RawTicket, calls the LLM client, parses the response,
and validates it into an AnalysisResult Pydantic model.
Enforces untrusted customer input handling and rejects filtered messages.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from pydantic import ValidationError

from feedback_analyzer.config import Config, get_config
from feedback_analyzer.filtering.filter import is_qualifying
from feedback_analyzer.llm.client import GroqClient, LLMResponseError
from feedback_analyzer.llm.prompts import SYSTEM_PROMPT, format_user_prompt
from feedback_analyzer.schemas.analysis_schema import AnalysisResult
from feedback_analyzer.schemas.input_schema import RawTicket

logger = logging.getLogger(__name__)


def _clean_json_payload(raw_text: str) -> str:
    """Strip markdown code fences and extraneous whitespace from LLM response text."""
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove first fence line (e.g. ```json or ```)
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        # Remove trailing fence line
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


class TicketAnalyzer:
    """
    Coordinates ticket prompt formatting, LLM execution, response parsing,
    and schema validation.
    """

    def __init__(
        self,
        config: Config | None = None,
        client: GroqClient | None = None,
    ) -> None:
        self.config = config or get_config()
        self.client = client or GroqClient(self.config)

    def analyze(self, ticket: RawTicket) -> AnalysisResult:
        """
        Analyze a qualified customer ticket using the LLM.

        Args:
            ticket: Validated RawTicket to be analyzed.

        Returns:
            Validated AnalysisResult containing category, priority, sentiment,
            product_or_feature, and suggested_reply.

        Raises:
            ValueError: If the ticket is filtered (not qualifying for LLM analysis).
            LLMError: If the LLM client fails (auth, timeout, rate limit).
            LLMResponseError: If the LLM produces malformed JSON or schema-invalid data.
        """
        # Requirement 10: Do not send filtered messages to the LLM
        qualifies, ignore_reason = is_qualifying(ticket)
        if not qualifies:
            raise ValueError(
                f"Cannot send filtered ticket '{ticket.ticket_id}' to LLM: "
                f"{ignore_reason}"
            )

        # Requirement 6: Treat customer message as untrusted input (safely wrapped)
        user_prompt = format_user_prompt(ticket.message)

        logger.info("Submitting ticket %s to LLM for classification", ticket.ticket_id)
        raw_response = self.client.generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        # Requirement 7: Handle malformed responses cleanly
        clean_text = _clean_json_payload(raw_response)
        try:
            parsed_data = json.loads(clean_text)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse JSON response for ticket %s: %s", ticket.ticket_id, exc)
            raise LLMResponseError(
                f"LLM returned malformed JSON for ticket '{ticket.ticket_id}': {exc}"
            ) from exc

        if not isinstance(parsed_data, dict):
            raise LLMResponseError(
                f"LLM returned JSON of type {type(parsed_data).__name__}, expected a JSON object"
            )

        # Requirement 5: Validate response with Pydantic and enforce permitted values
        try:
            result = AnalysisResult(
                category=parsed_data.get("category"),  # type: ignore[arg-type]
                priority=parsed_data.get("priority"),  # type: ignore[arg-type]
                sentiment=parsed_data.get("sentiment"),  # type: ignore[arg-type]
                product_or_feature=parsed_data.get("product_or_feature"),
                suggested_reply=parsed_data.get("suggested_reply"),  # type: ignore[arg-type]
                model_name=self.config.model_name,
                analyzed_at=datetime.now(UTC).isoformat(),
            )
        except ValidationError as exc:
            logger.error(
                "Schema validation failed on LLM output for ticket %s: %s",
                ticket.ticket_id,
                exc,
            )
            raise LLMResponseError(
                f"LLM output violated analysis schema for ticket '{ticket.ticket_id}': {exc}"
            ) from exc

        logger.info(
            "Ticket %s classified as %s (%s, %s)",
            ticket.ticket_id,
            result.category.value,
            result.priority.value,
            result.sentiment.value,
        )
        return result
