"""
schemas/input_schema.py
=======================
Pydantic v2 model for a raw ticket record as read from CSV or JSON.

Validates:
  - ticket_id: required, non-empty string after stripping whitespace.
  - message: required, non-empty string after stripping whitespace.
  - source: optional; coerced to str, defaults to "unknown".
  - created_at: optional ISO-8601 string; defaults to "".

Raises pydantic.ValidationError on invalid records.
The orchestrator catches ValidationError and marks the record INVALID.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class RawTicket(BaseModel):
    """Validated representation of a single inbound customer ticket."""

    ticket_id: str = Field(..., description="Unique ticket identifier from the input file.")
    message: str = Field(..., description="Raw customer message text.")
    source: str = Field(default="unknown", description="Origin channel, e.g. 'web', 'email'.")
    created_at: str = Field(
        default="",
        description="ISO-8601 timestamp string from the input file; empty string if absent.",
    )

    @field_validator("ticket_id", "message", mode="before")
    @classmethod
    def strip_and_require(cls, v: object) -> str:
        """Coerce to str, strip whitespace, and reject blank values."""
        if not isinstance(v, str):
            v = str(v)
        v = v.strip()
        if not v:
            raise ValueError("Value must be a non-empty string after stripping whitespace.")
        return v

    @field_validator("source", "created_at", mode="before")
    @classmethod
    def coerce_optional_to_str(cls, v: object) -> str:
        """Coerce optional fields to str; treat None as empty string."""
        if v is None:
            return ""
        return str(v).strip()
