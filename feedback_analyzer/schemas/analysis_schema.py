"""
schemas/analysis_schema.py
===========================
Pydantic model for the LLM structured output (AnalysisResult).
Enforces controlled vocabulary for Category, Priority, and Sentiment.
Validates nullable product_or_feature and suggested_reply.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from feedback_analyzer.constants import Category, Priority, Sentiment


class AnalysisResult(BaseModel):
    """
    Validated analysis result produced by the LLM for a customer ticket.
    Strictly enforces permitted values for category, priority, and sentiment.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    category: Category = Field(
        ...,
        description="Ticket category: Bug Report, Feature Request, Billing Issue, or General Inquiry",
    )
    priority: Priority = Field(
        ...,
        description="Ticket priority: Low, Medium, High, or Urgent",
    )
    sentiment: Sentiment = Field(
        ...,
        description="Customer sentiment: Positive, Neutral, or Negative",
    )
    product_or_feature: str | None = Field(
        default=None,
        description="Specific product or feature referenced in the ticket, or None if unspecified",
    )
    suggested_reply: str = Field(
        ...,
        description="A short, polite, context-specific suggested draft auto-reply",
        min_length=1,
    )
    model_name: str | None = Field(
        default=None,
        description="Name of the model used to produce this analysis",
    )
    analyzed_at: str | None = Field(
        default=None,
        description="ISO-8601 UTC timestamp of analysis",
    )

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, v: object) -> Category:
        """Allow case-insensitive matching for Category enums."""
        if isinstance(v, Category):
            return v
        if isinstance(v, str):
            clean = v.strip().lower().replace("_", " ")
            for member in Category:
                if member.value.lower() == clean:
                    return member
        # Fallback to standard validation which will raise ValidationError
        return v  # type: ignore[return-value]

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_priority(cls, v: object) -> Priority:
        """Allow case-insensitive matching for Priority enums."""
        if isinstance(v, Priority):
            return v
        if isinstance(v, str):
            clean = v.strip().lower()
            for member in Priority:
                if member.value.lower() == clean:
                    return member
        return v  # type: ignore[return-value]

    @field_validator("sentiment", mode="before")
    @classmethod
    def normalize_sentiment(cls, v: object) -> Sentiment:
        """Allow case-insensitive matching for Sentiment enums."""
        if isinstance(v, Sentiment):
            return v
        if isinstance(v, str):
            clean = v.strip().lower()
            for member in Sentiment:
                if member.value.lower() == clean:
                    return member
        return v  # type: ignore[return-value]

    @field_validator("product_or_feature", mode="before")
    @classmethod
    def normalize_product_or_feature(cls, v: object) -> str | None:
        """Convert empty strings, 'null', 'none', 'n/a' to None."""
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            if not s or s.lower() in {"none", "null", "n/a", "na", "unknown"}:
                return None
            return s
        return str(v)

    @field_validator("suggested_reply", mode="before")
    @classmethod
    def normalize_suggested_reply(cls, v: object) -> str:
        """Strip whitespace and reject blank reply strings."""
        if not isinstance(v, str):
            v = str(v)
        s = v.strip()
        if not s:
            raise ValueError("suggested_reply cannot be empty or whitespace-only")
        return s
