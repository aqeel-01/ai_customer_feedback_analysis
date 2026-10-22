"""
unit/test_repository.py
=======================
Unit tests for SQLite connection, schema creation, repository data access,
duplicate ID handling, error handling, and parameterized query security.
Uses an in-memory SQLite database for high-speed isolated tests.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from feedback_analyzer.constants import Category, Priority, ProcessingStatus, Sentiment
from feedback_analyzer.db.connection import connection_scope, get_connection
from feedback_analyzer.db.repository import (
    DatabaseError,
    DuplicateTicketError,
    get_analysis,
    get_status_counts,
    get_ticket,
    insert_analysis,
    insert_ticket,
    list_all_tickets_with_results,
    list_processed_tickets,
    ticket_exists,
)
from feedback_analyzer.schemas.analysis_schema import AnalysisResult


@pytest.fixture
def db_conn() -> sqlite3.Connection:
    """Fixture providing an in-memory database with schema initialized."""
    conn = get_connection(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def sample_analysis() -> AnalysisResult:
    return AnalysisResult(
        category=Category.BUG_REPORT,
        priority=Priority.HIGH,
        sentiment=Sentiment.NEGATIVE,
        product_or_feature="PDF Export",
        suggested_reply="Thank you for reporting this PDF issue. We are investigating it immediately.",
        model_name="llama-3.1-8b-instant",
        analyzed_at="2026-10-21T12:00:00Z",
    )


# --- 1. Connection & Schema Initialization Tests ---


class TestConnectionAndSchema:
    def test_tables_created_automatically(self, db_conn: sqlite3.Connection) -> None:
        cursor = db_conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row["name"] for row in cursor.fetchall()}
        assert "tickets" in tables
        assert "analysis_results" in tables

    def test_foreign_keys_pragma_enabled(self, db_conn: sqlite3.Connection) -> None:
        cursor = db_conn.cursor()
        cursor.execute("PRAGMA foreign_keys;")
        assert cursor.fetchone()[0] == 1

    def test_connection_scope_commits_and_closes(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with connection_scope(db_file) as conn:
            insert_ticket(
                conn,
                ticket_id="TCK-100",
                raw_message="App crashed.",
                processing_status=ProcessingStatus.PROCESSED,
            )

        # Reopen to verify commit persisted
        reopened = get_connection(db_file)
        assert ticket_exists(reopened, "TCK-100")
        reopened.close()

    def test_connection_scope_rolls_back_on_exception(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test_rollback.db"
        with pytest.raises(RuntimeError), connection_scope(db_file) as conn:
            insert_ticket(
                conn,
                ticket_id="TCK-FAIL",
                raw_message="Should rollback.",
                processing_status=ProcessingStatus.PROCESSED,
            )
            raise RuntimeError("Simulated failure")

        reopened = get_connection(db_file)
        assert not ticket_exists(reopened, "TCK-FAIL")
        reopened.close()


# --- 2. Ticket Insertion & Retrieval Tests ---


class TestTicketRepository:
    def test_insert_and_get_processed_ticket(self, db_conn: sqlite3.Connection) -> None:
        inserted = insert_ticket(
            db_conn,
            ticket_id="TCK-1",
            raw_message="Cannot login to dashboard.",
            processing_status=ProcessingStatus.PROCESSED,
            source_file="tickets.csv",
        )
        assert inserted is True
        row = get_ticket(db_conn, "TCK-1")
        assert row is not None
        assert row["ticket_id"] == "TCK-1"
        assert row["raw_message"] == "Cannot login to dashboard."
        assert row["processing_status"] == "PROCESSED"
        assert row["source_file"] == "tickets.csv"
        assert row["ignore_reason"] is None
        assert row["processed_at"] is not None

    def test_insert_ignored_ticket_with_reason(self, db_conn: sqlite3.Connection) -> None:
        insert_ticket(
            db_conn,
            ticket_id="TCK-2",
            raw_message="Hello!",
            processing_status=ProcessingStatus.IGNORED,
            ignore_reason="greeting or social pleasantry",
        )
        row = get_ticket(db_conn, "TCK-2")
        assert row is not None
        assert row["processing_status"] == "IGNORED"
        assert row["ignore_reason"] == "greeting or social pleasantry"

    def test_insert_invalid_ticket_with_reason(self, db_conn: sqlite3.Connection) -> None:
        insert_ticket(
            db_conn,
            ticket_id="TCK-3",
            raw_message="   ",
            processing_status=ProcessingStatus.INVALID,
            ignore_reason="missing message content",
        )
        row = get_ticket(db_conn, "TCK-3")
        assert row is not None
        assert row["processing_status"] == "INVALID"
        assert row["ignore_reason"] == "missing message content"

    def test_ticket_exists_returns_correct_boolean(self, db_conn: sqlite3.Connection) -> None:
        assert ticket_exists(db_conn, "NON-EXISTENT") is False
        insert_ticket(db_conn, "TCK-EXISTS", "A test", ProcessingStatus.PROCESSED)
        assert ticket_exists(db_conn, "TCK-EXISTS") is True


# --- 3. Duplicate Handling Tests ---


class TestDuplicateHandling:
    def test_duplicate_skip_default_returns_false_and_preserves_original(
        self, db_conn: sqlite3.Connection
    ) -> None:
        # First insertion
        first = insert_ticket(
            db_conn,
            ticket_id="DUP-1",
            raw_message="Original message",
            processing_status=ProcessingStatus.PROCESSED,
        )
        assert first is True

        # Second duplicate insertion with 'skip' (default)
        second = insert_ticket(
            db_conn,
            ticket_id="DUP-1",
            raw_message="Overwriting attempt",
            processing_status=ProcessingStatus.FAILED,
        )
        assert second is False

        # Verify original record unchanged
        row = get_ticket(db_conn, "DUP-1")
        assert row is not None
        assert row["raw_message"] == "Original message"
        assert row["processing_status"] == "PROCESSED"

    def test_duplicate_raise_mode_raises_duplicate_ticket_error(
        self, db_conn: sqlite3.Connection
    ) -> None:
        insert_ticket(db_conn, "DUP-STRICT", "First", ProcessingStatus.PROCESSED)
        with pytest.raises(DuplicateTicketError, match="already exists"):
            insert_ticket(
                db_conn,
                "DUP-STRICT",
                "Second",
                ProcessingStatus.PROCESSED,
                on_duplicate="raise",
            )


# --- 4. Analysis Results Insertion & Joins Tests ---


class TestAnalysisRepository:
    def test_insert_and_get_analysis(
        self, db_conn: sqlite3.Connection, sample_analysis: AnalysisResult
    ) -> None:
        insert_ticket(db_conn, "TCK-10", "Crash on export", ProcessingStatus.PROCESSED)
        insert_analysis(db_conn, "TCK-10", sample_analysis)

        analysis = get_analysis(db_conn, "TCK-10")
        assert analysis is not None
        assert analysis["ticket_id"] == "TCK-10"
        assert analysis["category"] == "Bug Report"
        assert analysis["priority"] == "High"
        assert analysis["sentiment"] == "Negative"
        assert analysis["product_feature"] == "PDF Export"
        assert "investigating" in analysis["suggested_reply"]
        assert analysis["model_name"] == "llama-3.1-8b-instant"

    def test_insert_analysis_foreign_key_violation_fails(
        self, db_conn: sqlite3.Connection, sample_analysis: AnalysisResult
    ) -> None:
        # TCK-NONEXISTENT does not exist in tickets table
        with pytest.raises(DatabaseError, match="FOREIGN KEY constraint failed"):
            insert_analysis(db_conn, "TCK-NONEXISTENT", sample_analysis)

    def test_list_processed_tickets_only_returns_processed(
        self, db_conn: sqlite3.Connection, sample_analysis: AnalysisResult
    ) -> None:
        # 1 Processed ticket
        insert_ticket(db_conn, "TCK-OK", "Crash on export", ProcessingStatus.PROCESSED)
        insert_analysis(db_conn, "TCK-OK", sample_analysis)

        # 1 Ignored greeting ticket (no analysis row)
        insert_ticket(db_conn, "TCK-GREET", "Hi there!", ProcessingStatus.IGNORED, "greeting")

        # 1 Failed ticket
        insert_ticket(db_conn, "TCK-ERR", "Bug", ProcessingStatus.FAILED, "API timeout")

        processed = list_processed_tickets(db_conn)
        assert len(processed) == 1
        assert processed[0]["ticket_id"] == "TCK-OK"
        assert processed[0]["raw_message"] == "Crash on export"
        assert processed[0]["category"] == "Bug Report"
        assert processed[0]["priority"] == "High"
        assert processed[0]["sentiment"] == "Negative"
        assert processed[0]["product_or_feature"] == "PDF Export"
        assert "investigating" in processed[0]["suggested_reply"]

    def test_list_all_tickets_keeps_ignored_and_failed_distinguishable(
        self, db_conn: sqlite3.Connection, sample_analysis: AnalysisResult
    ) -> None:
        insert_ticket(db_conn, "T1", "App crash", ProcessingStatus.PROCESSED)
        insert_analysis(db_conn, "T1", sample_analysis)
        insert_ticket(db_conn, "T2", "Good morning", ProcessingStatus.IGNORED, "social pleasantry")
        insert_ticket(db_conn, "T3", "Bad data", ProcessingStatus.INVALID, "missing id")
        insert_ticket(db_conn, "T4", "Server down", ProcessingStatus.FAILED, "rate limit exceeded")

        all_records = list_all_tickets_with_results(db_conn)
        assert len(all_records) == 4

        statuses = {r["ticket_id"]: r["processing_status"] for r in all_records}
        assert statuses["T1"] == "PROCESSED"
        assert statuses["T2"] == "IGNORED"
        assert statuses["T3"] == "INVALID"
        assert statuses["T4"] == "FAILED"

        reasons = {r["ticket_id"]: r["ignore_reason"] for r in all_records}
        assert reasons["T1"] is None
        assert reasons["T2"] == "social pleasantry"
        assert reasons["T3"] == "missing id"
        assert reasons["T4"] == "rate limit exceeded"

    def test_get_status_counts(self, db_conn: sqlite3.Connection) -> None:
        insert_ticket(db_conn, "T1", "msg", ProcessingStatus.PROCESSED)
        insert_ticket(db_conn, "T2", "msg", ProcessingStatus.PROCESSED)
        insert_ticket(db_conn, "T3", "msg", ProcessingStatus.IGNORED, "spam")
        insert_ticket(db_conn, "T4", "msg", ProcessingStatus.FAILED, "error")

        counts = get_status_counts(db_conn)
        assert counts["PROCESSED"] == 2
        assert counts["IGNORED"] == 1
        assert counts["INVALID"] == 0
        assert counts["FAILED"] == 1


# --- 5. Parameterized Query Security Test ---


class TestParameterizedQuerySecurity:
    def test_sql_injection_attempt_in_ticket_id(self, db_conn: sqlite3.Connection) -> None:
        malicious_id = "TCK-1'; DROP TABLE tickets; --"
        inserted = insert_ticket(
            db_conn,
            ticket_id=malicious_id,
            raw_message="Normal text",
            processing_status=ProcessingStatus.PROCESSED,
        )
        assert inserted is True

        # Ensure tickets table was NOT dropped
        assert ticket_exists(db_conn, malicious_id)
        row = get_ticket(db_conn, malicious_id)
        assert row is not None
        assert row["ticket_id"] == malicious_id
