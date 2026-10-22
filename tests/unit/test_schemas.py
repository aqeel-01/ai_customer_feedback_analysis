"""
unit/test_schemas.py
====================
Tests for feedback_analyzer.schemas.input_schema.RawTicket.

Covers:
  - Valid records with all fields
  - Optional field defaults
  - Type coercion (numeric ticket_id, None source)
  - Whitespace stripping
  - ValidationError on missing required fields
  - ValidationError on blank/empty required fields
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from feedback_analyzer.schemas.input_schema import RawTicket

# ---------------------------------------------------------------------------
# Valid records
# ---------------------------------------------------------------------------


class TestRawTicketValid:
    def test_all_fields_provided(self):
        ticket = RawTicket(
            ticket_id="T001",
            message="The app crashes on checkout.",
            source="web",
            created_at="2026-10-01T09:00:00Z",
        )
        assert ticket.ticket_id == "T001"
        assert ticket.message == "The app crashes on checkout."
        assert ticket.source == "web"
        assert ticket.created_at == "2026-10-01T09:00:00Z"

    def test_optional_fields_use_defaults(self):
        ticket = RawTicket(ticket_id="T002", message="App crashed.")
        assert ticket.source == "unknown"
        assert ticket.created_at == ""

    def test_numeric_ticket_id_coerced_to_str(self):
        """Integer ticket_id should be cast to a string, not rejected."""
        ticket = RawTicket(ticket_id=42, message="Some bug report.")
        assert ticket.ticket_id == "42"

    def test_none_source_coerced_to_empty_string(self):
        ticket = RawTicket(ticket_id="T003", message="Billing issue.", source=None)
        assert ticket.source == ""

    def test_none_created_at_coerced_to_empty_string(self):
        ticket = RawTicket(ticket_id="T004", message="Feature request.", created_at=None)
        assert ticket.created_at == ""

    def test_whitespace_stripped_from_ticket_id(self):
        ticket = RawTicket(ticket_id="  T005  ", message="Login broken.")
        assert ticket.ticket_id == "T005"

    def test_whitespace_stripped_from_message(self):
        ticket = RawTicket(ticket_id="T006", message="   App is down.   ")
        assert ticket.message == "App is down."

    def test_whitespace_only_source_coerced_to_empty_string(self):
        ticket = RawTicket(ticket_id="T007", message="Test.", source="   ")
        assert ticket.source == ""


# ---------------------------------------------------------------------------
# Invalid records — ValidationError expected
# ---------------------------------------------------------------------------


class TestRawTicketInvalid:
    def test_missing_ticket_id_raises_validation_error(self):
        with pytest.raises(ValidationError) as exc_info:
            RawTicket(message="Valid message.")
        assert "ticket_id" in str(exc_info.value)

    def test_missing_message_raises_validation_error(self):
        with pytest.raises(ValidationError) as exc_info:
            RawTicket(ticket_id="T001")
        assert "message" in str(exc_info.value)

    def test_blank_ticket_id_raises_validation_error(self):
        with pytest.raises(ValidationError):
            RawTicket(ticket_id="   ", message="Valid message.")

    def test_empty_ticket_id_raises_validation_error(self):
        with pytest.raises(ValidationError):
            RawTicket(ticket_id="", message="Valid message.")

    def test_blank_message_raises_validation_error(self):
        with pytest.raises(ValidationError):
            RawTicket(ticket_id="T001", message="   ")

    def test_empty_message_raises_validation_error(self):
        with pytest.raises(ValidationError):
            RawTicket(ticket_id="T001", message="")

    def test_both_required_fields_missing_raises_validation_error(self):
        with pytest.raises(ValidationError) as exc_info:
            RawTicket()
        errors = exc_info.value.errors()
        # Both ticket_id and message should be reported
        error_fields = {e["loc"][0] for e in errors}
        assert "ticket_id" in error_fields
        assert "message" in error_fields
