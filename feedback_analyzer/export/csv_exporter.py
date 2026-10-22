"""
export/csv_exporter.py
======================
Exports feedback analysis records to CSV format.
Ensures safe handling of special characters (quotes, commas, newlines, Unicode)
and safe creation of files when the result set is empty.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path
from typing import Any

# Core columns for processed tickets (original message + 5 AI extracted fields)
PROCESSED_CSV_FIELDS = [
    "ticket_id",
    "raw_message",
    "category",
    "priority",
    "sentiment",
    "product_or_feature",
    "suggested_reply",
    "model_name",
    "analyzed_at",
]

# Audit fields for all records (distinguishing IGNORED / INVALID / FAILED)
ALL_RECORDS_CSV_FIELDS = [
    "ticket_id",
    "raw_message",
    "processing_status",
    "ignore_reason",
    "category",
    "priority",
    "sentiment",
    "product_or_feature",
    "suggested_reply",
    "model_name",
    "analyzed_at",
]


def export_processed_to_csv(
    records: Sequence[dict[str, Any]],
    output_path: str | Path,
) -> Path:
    """
    Write successfully processed feedback tickets to a CSV file.

    Includes the original message and all 5 AI-extracted fields:
    category, priority, sentiment, product_or_feature, suggested_reply.

    Args:
        records: List of dictionaries matching processed ticket schema.
        output_path: Destination path for the CSV file.

    Returns:
        Path object of the written file.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=PROCESSED_CSV_FIELDS,
            extrasaction="ignore",
            quoting=csv.QUOTE_MINIMAL,
        )
        writer.writeheader()
        for row in records:
            # Normalize None values to empty strings for clean CSV representation
            clean_row = {
                k: ("" if row.get(k) is None else str(row.get(k)))
                for k in PROCESSED_CSV_FIELDS
            }
            writer.writerow(clean_row)

    return path


def export_all_records_to_csv(
    records: Sequence[dict[str, Any]],
    output_path: str | Path,
) -> Path:
    """
    Write all tickets (PROCESSED, IGNORED, INVALID, FAILED) to CSV.
    Keeps ignored, invalid, and failed records distinct from successful ones.

    Args:
        records: List of dictionaries matching the full audit schema.
        output_path: Destination path for the CSV file.

    Returns:
        Path object of the written file.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=ALL_RECORDS_CSV_FIELDS,
            extrasaction="ignore",
            quoting=csv.QUOTE_MINIMAL,
        )
        writer.writeheader()
        for row in records:
            clean_row = {
                k: ("" if row.get(k) is None else str(row.get(k)))
                for k in ALL_RECORDS_CSV_FIELDS
            }
            writer.writerow(clean_row)

    return path
