"""
orchestrator.py
===============
Central pipeline orchestrator for the AI Customer Feedback Analyzer.
Coordinates:
  1. Ingestion (CSV / JSON)
  2. Input Validation (Pydantic RawTicket)
  3. Stateless Message Filtering (greetings, spam, promotional)
  4. LLM Classification & Auto-Reply Generation
  5. SQLite Persistence (atomic, status-tracked, duplicate-safe)
  6. CSV & JSON Export (processed deliverables + full audit logs)
  7. Terminal Summary Reporting
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from feedback_analyzer.config import Config, get_config
from feedback_analyzer.constants import Category, Priority, ProcessingStatus, Sentiment
from feedback_analyzer.db.connection import get_connection
from feedback_analyzer.db.repository import (
    insert_analysis,
    insert_ticket,
    list_all_tickets_with_results,
    list_processed_tickets,
    ticket_exists,
)
from feedback_analyzer.export.csv_exporter import (
    export_all_records_to_csv,
    export_processed_to_csv,
)
from feedback_analyzer.export.json_exporter import (
    export_all_records_to_json,
    export_processed_to_json,
)
from feedback_analyzer.filtering.filter import is_qualifying
from feedback_analyzer.ingestion import load_records
from feedback_analyzer.llm.analyzer import TicketAnalyzer
from feedback_analyzer.schemas.analysis_schema import AnalysisResult
from feedback_analyzer.schemas.input_schema import RawTicket

logger = logging.getLogger(__name__)


@dataclass
class ProcessingSummary:
    """Summary metrics of an orchestrator processing run."""

    total_records: int = 0
    valid_records: int = 0
    invalid_records: int = 0
    ignored_records: int = 0
    processed_records: int = 0
    failed_records: int = 0
    skipped_duplicates: int = 0
    db_path: str = ""
    csv_export_path: str | None = None
    json_export_path: str | None = None


class MockTicketAnalyzer:
    """
    Offline mock analyzer for test environments and offline verification.
    Produces deterministic, schema-compliant AnalysisResult objects without API keys.
    """

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or get_config()

    def analyze(self, ticket: RawTicket) -> AnalysisResult:
        qualifies, reason = is_qualifying(ticket)
        if not qualifies:
            raise ValueError(f"Cannot send filtered ticket '{ticket.ticket_id}' to LLM: {reason}")

        text = ticket.message.lower()

        if any(w in text for w in ["crash", "broken", "bug", "error", "fails", "freeze"]):
            category = Category.BUG_REPORT
            priority = (
                Priority.URGENT
                if ("payment" in text or "checkout" in text or "asap" in text)
                else (Priority.HIGH if "crash" in text or "freeze" in text else Priority.MEDIUM)
            )
            sentiment = Sentiment.NEGATIVE
            feature = "payment page" if "payment" in text else ("search" if "search" in text else None)
            reply = f"Thank you for reporting this issue with {feature or 'the application'}. Our engineering team is investigating immediately."
        elif any(w in text for w in ["dark mode", "feature", "add", "suggest", "could you"]):
            category = Category.FEATURE_REQUEST
            priority = Priority.MEDIUM
            sentiment = Sentiment.POSITIVE
            feature = "dark mode" if "dark mode" in text else "requested feature"
            reply = f"Thank you for suggesting {feature}! We have shared this with our product roadmap team."
        elif any(w in text for w in ["charge", "charged", "invoice", "refund", "subscription", "billing", "payment"]):
            category = Category.BILLING_ISSUE
            priority = Priority.URGENT if "twice" in text or "refund" in text else Priority.HIGH
            sentiment = Sentiment.NEGATIVE
            feature = "subscription billing"
            reply = "We apologize for the billing discrepancy. Our finance team is reviewing your account and will issue any due refunds promptly."
        else:
            category = Category.GENERAL_INQUIRY
            priority = Priority.LOW
            sentiment = Sentiment.NEUTRAL
            feature = "CSV export" if "export" in text or "csv" in text else None
            reply = "Hello, thank you for contacting us. You can find full guidance in our user documentation."

        return AnalysisResult(
            category=category,
            priority=priority,
            sentiment=sentiment,
            product_or_feature=feature,
            suggested_reply=reply,
            model_name=f"{self.config.model_name}-offline-mock",
        )


def format_summary_report(summary: ProcessingSummary) -> str:
    """Generate a clean, aligned summary table for the console."""
    lines = [
        "",
        "=" * 64,
        "          AI CUSTOMER FEEDBACK ANALYZER - RUN SUMMARY",
        "=" * 64,
        f"  Total Input Records:          {summary.total_records:>6}",
        f"  - Valid Input Records:        {summary.valid_records:>6}",
        f"  - Invalid Input Records:      {summary.invalid_records:>6}",
        f"  - Ignored (Greetings/Spam):   {summary.ignored_records:>6}",
        f"  - Successfully Analyzed:      {summary.processed_records:>6}",
        f"  - Failed (API/Analysis Error):{summary.failed_records:>6}",
        f"  - Duplicate Records Skipped:  {summary.skipped_duplicates:>6}",
        "-" * 64,
        f"  SQLite Database:              {summary.db_path}",
    ]
    if summary.csv_export_path:
        lines.append(f"  CSV Results:                  {summary.csv_export_path}")
    if summary.json_export_path:
        lines.append(f"  JSON Results:                 {summary.json_export_path}")
    lines.append("=" * 64)
    lines.append("")
    return "\n".join(lines)


def run_pipeline(
    input_path: str | Path,
    output_dir: str | Path | None = None,
    db_path: str | Path | None = None,
    export_format: str = "both",
    mock_mode: bool = False,
    config: Config | None = None,
    analyzer: TicketAnalyzer | MockTicketAnalyzer | None = None,
) -> ProcessingSummary:
    """
    Run the end-to-end feedback analysis pipeline.

    Args:
        input_path: Path to input CSV or JSON file.
        output_dir: Destination folder for output files (default from config).
        db_path: Path to SQLite DB file (default from config).
        export_format: 'csv', 'json', or 'both'.
        mock_mode: If True, uses offline mock analyzer (no API key required).
        config: Optional Config override.
        analyzer: Optional pre-configured TicketAnalyzer or MockTicketAnalyzer.

    Returns:
        ProcessingSummary instance containing execution metrics.
    """
    cfg = config or get_config()
    out_dir = Path(output_dir or cfg.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    actual_db_path = str(db_path or cfg.db_path)

    summary = ProcessingSummary(db_path=actual_db_path)

    logger.info("Starting analysis pipeline for file: %s", input_path)
    raw_records = load_records(input_path)
    logger.info("Loaded %d raw records from %s", len(raw_records), input_path)

    # Initialize analyzer
    if analyzer is None:
        if mock_mode:
            logger.info("Initializing in OFFLINE / MOCK mode (no external API calls)")
            analyzer = MockTicketAnalyzer(cfg)
        else:
            analyzer = TicketAnalyzer(cfg)

    # Process all records with isolated per-record error handling
    conn = get_connection(actual_db_path)
    try:
        for idx, raw_dict in enumerate(raw_records, start=1):
            summary.total_records += 1

            # Step 1: Input Validation
            try:
                # Clean non-string or None keys from malformed CSV rows
                clean_dict = {str(k): v for k, v in raw_dict.items() if k is not None}
                ticket = RawTicket(**clean_dict)
                summary.valid_records += 1
            except (ValidationError, TypeError, ValueError) as val_err:
                summary.invalid_records += 1
                fallback_id = str(raw_dict.get("ticket_id") or f"INVALID_ROW_{idx}")
                fallback_msg = str(raw_dict.get("message") or "")
                if isinstance(val_err, ValidationError):
                    err_msg = f"Validation error: {val_err.errors()[0].get('msg', 'invalid fields')}"
                else:
                    err_msg = f"Malformed record format: {val_err}"
                logger.warning("Record #%d (%s) failed validation: %s", idx, fallback_id, err_msg)
                insert_ticket(
                    conn,
                    ticket_id=fallback_id,
                    raw_message=fallback_msg,
                    processing_status=ProcessingStatus.INVALID,
                    ignore_reason=err_msg,
                    source_file=str(input_path),
                )
                conn.commit()
                continue

            # Step 2: Avoid duplicate processing
            if ticket_exists(conn, ticket.ticket_id):
                summary.skipped_duplicates += 1
                logger.info("Ticket %s already exists in database; skipping duplicate.", ticket.ticket_id)
                continue

            # Step 3: Stateless Message Filtering
            qualifies, ignore_reason = is_qualifying(ticket)
            if not qualifies:
                summary.ignored_records += 1
                logger.info("Ticket %s ignored by filter: %s", ticket.ticket_id, ignore_reason)
                insert_ticket(
                    conn,
                    ticket_id=ticket.ticket_id,
                    raw_message=ticket.message,
                    processing_status=ProcessingStatus.IGNORED,
                    ignore_reason=ignore_reason,
                    source_file=str(input_path),
                    created_at=ticket.created_at or None,
                )
                conn.commit()
                continue

            # Step 4: LLM Analysis & Output Validation
            try:
                analysis = analyzer.analyze(ticket)
                # Store processed record and analysis atomically
                insert_ticket(
                    conn,
                    ticket_id=ticket.ticket_id,
                    raw_message=ticket.message,
                    processing_status=ProcessingStatus.PROCESSED,
                    source_file=str(input_path),
                    created_at=ticket.created_at or None,
                )
                insert_analysis(conn, ticket.ticket_id, analysis)
                conn.commit()
                summary.processed_records += 1
                logger.info("Successfully processed ticket %s: [%s]", ticket.ticket_id, analysis.category.value)
            except Exception as exc:  # noqa: BLE001
                summary.failed_records += 1
                error_desc = f"Analysis failed: {exc}"
                logger.error("Failed to analyze ticket %s: %s", ticket.ticket_id, exc)
                # Never classify failed API calls as successful analyses!
                insert_ticket(
                    conn,
                    ticket_id=ticket.ticket_id,
                    raw_message=ticket.message,
                    processing_status=ProcessingStatus.FAILED,
                    ignore_reason=error_desc,
                    source_file=str(input_path),
                    created_at=ticket.created_at or None,
                )
                conn.commit()
                continue

        # Step 5: Exporting Results
        processed_tickets = list_processed_tickets(conn)
        all_tickets = list_all_tickets_with_results(conn)

        export_fmt = export_format.lower().strip()
        if export_fmt in {"csv", "both"}:
            csv_path = out_dir / "results.csv"
            export_processed_to_csv(processed_tickets, csv_path)
            export_all_records_to_csv(all_tickets, out_dir / "all_tickets.csv")
            summary.csv_export_path = str(csv_path)

        if export_fmt in {"json", "both"}:
            json_path = out_dir / "results.json"
            export_processed_to_json(processed_tickets, json_path)
            export_all_records_to_json(all_tickets, out_dir / "all_tickets.json")
            summary.json_export_path = str(json_path)

    finally:
        conn.close()

    print(format_summary_report(summary))
    return summary
