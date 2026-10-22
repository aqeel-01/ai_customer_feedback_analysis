"""
db/repository.py
================
Data access layer for SQLite.
All database access is performed through parameterized SQL queries.
Handles duplicate ticket IDs predictably (skip and log), enforces transactions,
and provides query helpers for processed and audit records.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from typing import Any

from feedback_analyzer.constants import ProcessingStatus
from feedback_analyzer.schemas.analysis_schema import AnalysisResult

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Base exception for repository operations."""


class DuplicateTicketError(DatabaseError):
    """Raised when an attempt is made to insert a duplicate ticket ID in strict mode."""


def ticket_exists(conn: sqlite3.Connection, ticket_id: str) -> bool:
    """Return True if a ticket with the given ID already exists in the database."""
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM tickets WHERE ticket_id = ? LIMIT 1;", (ticket_id,))
    return cursor.fetchone() is not None


def insert_ticket(
    conn: sqlite3.Connection,
    ticket_id: str,
    raw_message: str,
    processing_status: ProcessingStatus | str,
    ignore_reason: str | None = None,
    source_file: str | None = None,
    created_at: str | None = None,
    processed_at: str | None = None,
    on_duplicate: str = "skip",
) -> bool:
    """
    Insert a ticket record into the 'tickets' table using parameterized SQL.

    Args:
        conn: Open SQLite connection.
        ticket_id: Unique identifier for the ticket.
        raw_message: The original, unmodified customer message.
        processing_status: ProcessingStatus enum or valid string (PROCESSED, IGNORED, etc.).
        ignore_reason: Explanation if IGNORED, INVALID, or FAILED.
        source_file: Originating input file path or name.
        created_at: Creation timestamp from input if available.
        processed_at: Timestamp when processed by system (defaults to current UTC ISO-8601).
        on_duplicate: How to handle duplicate IDs: 'skip' (default) or 'raise'.

    Returns:
        True if inserted, False if skipped due to existing duplicate.

    Raises:
        DuplicateTicketError: If on_duplicate='raise' and ticket_id exists.
        DatabaseError: If insertion fails.
    """
    status_str = (
        processing_status.value
        if isinstance(processing_status, ProcessingStatus)
        else str(processing_status)
    )

    if ticket_exists(conn, ticket_id):
        if on_duplicate == "raise":
            raise DuplicateTicketError(
                f"Ticket with ID '{ticket_id}' already exists in the database."
            )
        logger.warning(
            "Duplicate ticket_id '%s' found — skipping insertion to preserve original record.",
            ticket_id,
        )
        return False

    if processed_at is None:
        processed_at = datetime.now(UTC).isoformat()

    sql = """
        INSERT INTO tickets (
            ticket_id,
            raw_message,
            source_file,
            processing_status,
            ignore_reason,
            created_at,
            processed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?);
    """

    try:
        conn.execute(
            sql,
            (
                ticket_id,
                raw_message,
                source_file,
                status_str,
                ignore_reason,
                created_at,
                processed_at,
            ),
        )
        logger.debug("Inserted ticket '%s' with status '%s'", ticket_id, status_str)
        return True
    except sqlite3.Error as e:
        logger.error("Failed to insert ticket '%s': %s", ticket_id, e)
        raise DatabaseError(f"Database error inserting ticket '{ticket_id}': {e}") from e


def insert_analysis(
    conn: sqlite3.Connection,
    ticket_id: str,
    analysis: AnalysisResult,
) -> None:
    """
    Insert or update an analysis record in the 'analysis_results' table.

    Args:
        conn: Open SQLite connection.
        ticket_id: Foreign key referencing tickets.ticket_id.
        analysis: Validated AnalysisResult Pydantic model.

    Raises:
        DatabaseError: If insertion fails (e.g. FK constraint violation).
    """
    analyzed_at = analysis.analyzed_at or datetime.now(UTC).isoformat()

    sql = """
        INSERT OR REPLACE INTO analysis_results (
            ticket_id,
            category,
            priority,
            sentiment,
            product_feature,
            suggested_reply,
            model_name,
            analyzed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """

    try:
        conn.execute(
            sql,
            (
                ticket_id,
                analysis.category.value,
                analysis.priority.value,
                analysis.sentiment.value,
                analysis.product_or_feature,
                analysis.suggested_reply,
                analysis.model_name,
                analyzed_at,
            ),
        )
        logger.debug("Inserted analysis for ticket '%s'", ticket_id)
    except sqlite3.Error as e:
        logger.error("Failed to insert analysis for ticket '%s': %s", ticket_id, e)
        raise DatabaseError(f"Database error inserting analysis for '{ticket_id}': {e}") from e


def get_ticket(conn: sqlite3.Connection, ticket_id: str) -> dict[str, Any] | None:
    """Retrieve a single ticket record as a dictionary, or None if not found."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tickets WHERE ticket_id = ?;", (ticket_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


def get_analysis(conn: sqlite3.Connection, ticket_id: str) -> dict[str, Any] | None:
    """Retrieve analysis record for a ticket as a dictionary, or None if not found."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM analysis_results WHERE ticket_id = ?;", (ticket_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


def list_processed_tickets(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """
    Retrieve all successfully processed tickets joined with their AI analysis results.
    Returns the original message and all 5 AI-extracted fields:
    category, priority, sentiment, product_or_feature, suggested_reply.
    """
    sql = """
        SELECT
            t.ticket_id,
            t.raw_message,
            a.category,
            a.priority,
            a.sentiment,
            a.product_feature AS product_or_feature,
            a.suggested_reply,
            a.model_name,
            a.analyzed_at,
            t.source_file,
            t.created_at,
            t.processed_at
        FROM tickets t
        INNER JOIN analysis_results a ON t.ticket_id = a.ticket_id
        WHERE t.processing_status = 'PROCESSED'
        ORDER BY t.rowid ASC;
    """
    cursor = conn.cursor()
    cursor.execute(sql)
    return [dict(row) for row in cursor.fetchall()]


def list_all_tickets_with_results(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """
    Retrieve all tickets (PROCESSED, IGNORED, INVALID, FAILED) with their analysis
    results if available. Distinguishes successful analyses from ignored/failed records.
    """
    sql = """
        SELECT
            t.ticket_id,
            t.raw_message,
            t.processing_status,
            t.ignore_reason,
            a.category,
            a.priority,
            a.sentiment,
            a.product_feature AS product_or_feature,
            a.suggested_reply,
            a.model_name,
            a.analyzed_at,
            t.source_file,
            t.created_at,
            t.processed_at
        FROM tickets t
        LEFT JOIN analysis_results a ON t.ticket_id = a.ticket_id
        ORDER BY t.rowid ASC;
    """
    cursor = conn.cursor()
    cursor.execute(sql)
    return [dict(row) for row in cursor.fetchall()]


def get_status_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Return a dictionary mapping processing_status to count of tickets."""
    cursor = conn.cursor()
    cursor.execute("SELECT processing_status, COUNT(*) as count FROM tickets GROUP BY processing_status;")
    counts = {status.value: 0 for status in ProcessingStatus}
    for row in cursor.fetchall():
        counts[row["processing_status"]] = row["count"]
    return counts
