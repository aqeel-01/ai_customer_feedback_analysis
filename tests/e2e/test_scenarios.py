"""
e2e/test_scenarios.py
=====================
End-to-end integration tests verifying core customer support workflows and boundary cases:
1. Urgent bug report workflow (checkout/payment crash)
2. Feature request workflow (greeting-prefixed enhancement request)
3. Conversational noise filtering (greeting pleasantry with zero LLM invocations)
4. Billing issues and general inquiries
5. Nullable product names and defaults
6. API failures and malformed model output resilience
7. Input record validation and duplicate detection
8. SQLite database persistence and CSV/JSON exports
9. Live LLM execution (conditional on API key)
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from feedback_analyzer.config import Config
from feedback_analyzer.constants import Category, Priority, Sentiment
from feedback_analyzer.db.connection import get_connection
from feedback_analyzer.db.repository import (
    list_all_tickets_with_results,
)
from feedback_analyzer.filtering.filter import is_qualifying
from feedback_analyzer.llm.analyzer import TicketAnalyzer
from feedback_analyzer.orchestrator import run_pipeline
from feedback_analyzer.schemas.input_schema import RawTicket

# --- 1. Core Ticket Workflow Tests ---


class TestCoreTicketWorkflows:
    def test_urgent_bug_report_payment_crash(self, tmp_path: Path) -> None:
        """Urgent checkout crash report must classify as Bug Report, Urgent, Negative."""
        msg = "The payment page crashes every time I click 'Checkout' on Chrome. Please fix this ASAP!"
        ticket = RawTicket(ticket_id="TCK-CHECKOUT-01", message=msg)

        # 1. Filter allows it
        qualifies, reason = is_qualifying(ticket)
        assert qualifies is True
        assert reason == ""

        # 2. Mock LLM analyzes it with exact expected classifications
        mock_client = MagicMock()
        mock_client.generate.return_value = json.dumps({
            "category": "Bug Report",
            "priority": "Urgent",
            "sentiment": "Negative",
            "product_or_feature": "payment page",
            "suggested_reply": "We apologize for the checkout crash. Our engineering team is investigating this urgently.",
        })
        analyzer = TicketAnalyzer(client=mock_client)
        result = analyzer.analyze(ticket)

        assert result.category == Category.BUG_REPORT
        assert result.priority == Priority.URGENT
        assert result.sentiment == Sentiment.NEGATIVE
        assert result.product_or_feature == "payment page"
        assert "investigating" in result.suggested_reply

    def test_feature_request_with_greeting_dark_mode(self) -> None:
        """Greeting-prefixed request must classify as Feature Request, Medium, Positive."""
        msg = "Hi team, it would be awesome if you could add a dark mode to the mobile app."
        ticket = RawTicket(ticket_id="TCK-FEATURE-01", message=msg)

        # Filter must preserve requests even when prefixed with greeting
        qualifies, reason = is_qualifying(ticket)
        assert qualifies is True
        assert reason == ""

        mock_client = MagicMock()
        mock_client.generate.return_value = json.dumps({
            "category": "Feature Request",
            "priority": "Medium",
            "sentiment": "Positive",
            "product_or_feature": "dark mode",
            "suggested_reply": "Thank you for the idea! Dark mode is on our roadmap.",
        })
        analyzer = TicketAnalyzer(client=mock_client)
        result = analyzer.analyze(ticket)

        assert result.category == Category.FEATURE_REQUEST
        assert result.priority == Priority.MEDIUM
        assert result.sentiment == Sentiment.POSITIVE
        assert result.product_or_feature == "dark mode"

    def test_conversational_pleasantry_filtered_without_llm_call(self) -> None:
        """Pure conversational pleasantry must be ignored without invoking the LLM."""
        msg = "Hello, hope you are having a nice day!"
        ticket = RawTicket(ticket_id="TCK-GREETING-01", message=msg)

        # Must be rejected by the stateless filter
        qualifies, reason = is_qualifying(ticket)
        assert qualifies is False
        assert "greeting" in reason or "social pleasantry" in reason

        # Analyzer refuses to send filtered ticket to LLM
        mock_client = MagicMock()
        analyzer = TicketAnalyzer(client=mock_client)
        with pytest.raises(ValueError, match="Cannot send filtered ticket"):
            analyzer.analyze(ticket)

        # Assert no API call was made
        mock_client.generate.assert_not_called()


# --- 2. Category Workflows: Billing & General Inquiries ---


class TestAdditionalTaxonomies:
    def test_billing_issue_classification(self) -> None:
        ticket = RawTicket(
            ticket_id="TCK-BILLING",
            message="I was charged twice for invoice #4421 this month. Please refund the duplicate charge.",
        )
        mock_client = MagicMock()
        mock_client.generate.return_value = json.dumps({
            "category": "Billing Issue",
            "priority": "Urgent",
            "sentiment": "Negative",
            "product_or_feature": "subscription invoice",
            "suggested_reply": "We are processing your refund immediately.",
        })
        analyzer = TicketAnalyzer(client=mock_client)
        result = analyzer.analyze(ticket)
        assert result.category == Category.BILLING_ISSUE
        assert result.priority == Priority.URGENT
        assert result.sentiment == Sentiment.NEGATIVE

    def test_general_inquiry_with_nullable_product_feature(self) -> None:
        ticket = RawTicket(
            ticket_id="TCK-GENERAL",
            message="Where can I find your API documentation and user guide?",
        )
        mock_client = MagicMock()
        mock_client.generate.return_value = json.dumps({
            "category": "General Inquiry",
            "priority": "Low",
            "sentiment": "Neutral",
            "product_or_feature": None,
            "suggested_reply": "Documentation is available at https://docs.example.com.",
        })
        analyzer = TicketAnalyzer(client=mock_client)
        result = analyzer.analyze(ticket)
        assert result.category == Category.GENERAL_INQUIRY
        assert result.priority == Priority.LOW
        assert result.sentiment == Sentiment.NEUTRAL
        assert result.product_or_feature is None


# --- 3. End-to-End Resilience & Pipeline Verification ---


class TestPipelineResilienceAndPersistence:
    def test_complete_resilience_matrix(self, tmp_path: Path) -> None:
        """
        Creates a test dataset containing:
        - 1 valid bug report (Scenario 1)
        - 1 valid feature request (Scenario 2)
        - 1 pure greeting (Scenario 3 -> IGNORED)
        - 1 promotional spam (-> IGNORED)
        - 1 billing issue with API failure (-> FAILED)
        - 1 general inquiry with malformed LLM response (-> FAILED)
        - 1 invalid input record (missing ID -> INVALID)
        - 1 duplicate record (-> SKIPPED)
        """
        test_file = tmp_path / "comprehensive_input.json"
        records = [
            {"ticket_id": "T1", "message": "The payment page crashes every time I click 'Checkout' on Chrome. Please fix this ASAP!"},
            {"ticket_id": "T2", "message": "Hi team, it would be awesome if you could add a dark mode to the mobile app."},
            {"ticket_id": "T3", "message": "Hello, hope you are having a nice day!"},
            {"ticket_id": "T4", "message": "BUY NOW 50% OFF TODAY ONLY CLICK HERE"},
            {"ticket_id": "T5", "message": "I was charged twice for invoice #4421 this month. Please refund."},
            {"ticket_id": "T6", "message": "Where can I find your API documentation?"},
            {"ticket_id": "", "message": "Invalid record with empty ID"},
        ]
        test_file.write_text(json.dumps(records), encoding="utf-8")

        db_path = tmp_path / "e2e_feedback.db"
        output_dir = tmp_path / "e2e_output"

        # Mock analyzer where T5 raises API failure and T6 returns bad JSON
        mock_client = MagicMock()

        def mock_generate(system_prompt: str, user_prompt: str) -> str:
            if "charged twice" in user_prompt:
                raise RuntimeError("Temporary Groq API network timeout")
            if "API documentation" in user_prompt:
                return "Not valid JSON at all! {broken"
            if "payment page crashes" in user_prompt:
                return json.dumps({
                    "category": "Bug Report",
                    "priority": "Urgent",
                    "sentiment": "Negative",
                    "product_or_feature": "payment page",
                    "suggested_reply": "Investigating the checkout crash ASAP.",
                })
            if "dark mode" in user_prompt:
                return json.dumps({
                    "category": "Feature Request",
                    "priority": "Medium",
                    "sentiment": "Positive",
                    "product_or_feature": "dark mode",
                    "suggested_reply": "Dark mode is planned.",
                })
            return "{}"

        mock_client.generate.side_effect = mock_generate
        analyzer = TicketAnalyzer(client=mock_client)

        summary = run_pipeline(
            input_path=test_file,
            output_dir=output_dir,
            db_path=db_path,
            export_format="both",
            analyzer=analyzer,
        )

        # Metrics check
        assert summary.total_records == 7
        assert summary.valid_records == 6
        assert summary.invalid_records == 1
        assert summary.ignored_records == 2  # T3 (greeting), T4 (spam)
        assert summary.processed_records == 2  # T1, T2
        assert summary.failed_records == 2  # T5 (timeout), T6 (bad JSON)
        assert summary.skipped_duplicates == 0

        # Database checks
        conn = get_connection(db_path)
        all_rows = list_all_tickets_with_results(conn)
        assert len(all_rows) == 7

        by_id = {r["ticket_id"]: r for r in all_rows}
        assert by_id["T1"]["processing_status"] == "PROCESSED"
        assert by_id["T1"]["category"] == "Bug Report"
        assert by_id["T1"]["priority"] == "Urgent"

        assert by_id["T2"]["processing_status"] == "PROCESSED"
        assert by_id["T2"]["category"] == "Feature Request"

        assert by_id["T3"]["processing_status"] == "IGNORED"
        assert by_id["T4"]["processing_status"] == "IGNORED"

        assert by_id["T5"]["processing_status"] == "FAILED"
        assert "Temporary Groq API" in by_id["T5"]["ignore_reason"]

        assert by_id["T6"]["processing_status"] == "FAILED"
        assert "malformed JSON" in by_id["T6"]["ignore_reason"]

        assert "INVALID_ROW_7" in by_id or "" in by_id

        # Verify duplicate run: running again should skip all 7 records
        rerun_summary = run_pipeline(
            input_path=test_file,
            output_dir=output_dir,
            db_path=db_path,
            export_format="both",
            analyzer=analyzer,
        )
        assert rerun_summary.skipped_duplicates >= 6
        assert rerun_summary.processed_records == 0

        conn.close()

        # Export checks
        results_csv = output_dir / "results.csv"
        results_json = output_dir / "results.json"
        all_csv = output_dir / "all_tickets.csv"

        assert results_csv.exists()
        assert results_json.exists()
        assert all_csv.exists()

        # Processed results contain exactly the 2 processed tickets
        with results_csv.open("r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
            assert len(reader) == 2
            assert reader[0]["ticket_id"] == "T1"
            assert reader[0]["priority"] == "Urgent"
            assert reader[1]["ticket_id"] == "T2"

        # All tickets CSV retains distinction of IGNORED, INVALID, FAILED
        with all_csv.open("r", encoding="utf-8") as f:
            all_reader = list(csv.DictReader(f))
            assert len(all_reader) == 7
            statuses = {r["ticket_id"]: r["processing_status"] for r in all_reader}
            assert statuses["T1"] == "PROCESSED"
            assert statuses["T3"] == "IGNORED"
            assert statuses["T5"] == "FAILED"


# --- 4. Live API Test (Executed ONLY if valid GROQ_API_KEY is configured) ---


class TestLiveLLMIntegration:
    @pytest.mark.skipif(
        not os.getenv("GROQ_API_KEY")
        or os.getenv("GROQ_API_KEY") in {"", "your_groq_api_key_here"},
        reason="No valid GROQ_API_KEY found in environment or .env — skipping live API test",
    )
    def test_live_groq_api_call(self) -> None:
        """Runs against live Groq API only when credentials are provided."""
        cfg = Config.from_env()
        cfg.validate_for_llm()
        analyzer = TicketAnalyzer(cfg)
        ticket = RawTicket(
            ticket_id="LIVE-001",
            message="The payment page crashes every time I click 'Checkout' on Chrome. Please fix this ASAP!",
        )
        result = analyzer.analyze(ticket)
        assert result.category == Category.BUG_REPORT
        assert result.priority in {Priority.HIGH, Priority.URGENT}
        assert result.sentiment == Sentiment.NEGATIVE
        assert len(result.suggested_reply) > 5
