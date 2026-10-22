"""
integration/test_exporters.py
==============================
Tests for CSV and JSON exporters.
Verifies:
  - Processed tickets export contains original message + all 5 AI-extracted fields
  - Ignored and failed records are clearly distinguishable
  - Handling of empty result sets without errors
  - Safe handling of special characters (quotes, commas, newlines, Unicode, emojis)
  - Round-trip fidelity (write -> read back -> verify content matches)
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from feedback_analyzer.export.csv_exporter import (
    PROCESSED_CSV_FIELDS,
    export_all_records_to_csv,
    export_processed_to_csv,
)
from feedback_analyzer.export.json_exporter import (
    export_all_records_to_json,
    export_processed_to_json,
)


@pytest.fixture
def sample_processed_records() -> list[dict]:
    return [
        {
            "ticket_id": "TCK-101",
            "raw_message": "The application crashes when clicking the PDF export button.",
            "category": "Bug Report",
            "priority": "High",
            "sentiment": "Negative",
            "product_or_feature": "PDF Export",
            "suggested_reply": "Thank you for reporting. We are investigating the crash.",
            "model_name": "llama-3.1-8b-instant",
            "analyzed_at": "2026-10-21T10:00:00Z",
        },
        {
            "ticket_id": "TCK-102",
            "raw_message": "Hi, please add dark mode support in the mobile app.",
            "category": "Feature Request",
            "priority": "Medium",
            "sentiment": "Positive",
            "product_or_feature": "Dark Mode",
            "suggested_reply": "Thanks for the feedback! Dark mode is on our roadmap.",
            "model_name": "llama-3.1-8b-instant",
            "analyzed_at": "2026-10-21T10:05:00Z",
        },
        {
            "ticket_id": "TCK-103",
            "raw_message": "Where can I find documentation?",
            "category": "General Inquiry",
            "priority": "Low",
            "sentiment": "Neutral",
            "product_or_feature": None,
            "suggested_reply": "Our documentation is available at https://docs.example.com.",
            "model_name": "llama-3.1-8b-instant",
            "analyzed_at": "2026-10-21T10:10:00Z",
        },
    ]


@pytest.fixture
def sample_all_records() -> list[dict]:
    return [
        {
            "ticket_id": "TCK-201",
            "raw_message": "Crash on upload",
            "processing_status": "PROCESSED",
            "ignore_reason": None,
            "category": "Bug Report",
            "priority": "High",
            "sentiment": "Negative",
            "product_or_feature": "Upload",
            "suggested_reply": "We are fixing it.",
            "model_name": "llama-3.1-8b-instant",
            "analyzed_at": "2026-10-21T11:00:00Z",
        },
        {
            "ticket_id": "TCK-202",
            "raw_message": "Good morning team!",
            "processing_status": "IGNORED",
            "ignore_reason": "greeting or social pleasantry with no actionable content",
            "category": None,
            "priority": None,
            "sentiment": None,
            "product_or_feature": None,
            "suggested_reply": None,
            "model_name": None,
            "analyzed_at": None,
        },
        {
            "ticket_id": "TCK-203",
            "raw_message": "BUY NOW 50% DISCOUNT",
            "processing_status": "IGNORED",
            "ignore_reason": "spam or promotional broadcast",
            "category": None,
            "priority": None,
            "sentiment": None,
            "product_or_feature": None,
            "suggested_reply": None,
            "model_name": None,
            "analyzed_at": None,
        },
        {
            "ticket_id": "TCK-204",
            "raw_message": "Server timeout occurred",
            "processing_status": "FAILED",
            "ignore_reason": "LLM API timeout after 3 retries",
            "category": None,
            "priority": None,
            "sentiment": None,
            "product_or_feature": None,
            "suggested_reply": None,
            "model_name": None,
            "analyzed_at": None,
        },
    ]


# --- 1. Processed Records Export Tests ---


class TestProcessedExports:
    def test_export_processed_to_csv_contains_all_fields(
        self, tmp_path: Path, sample_processed_records: list[dict]
    ) -> None:
        csv_file = tmp_path / "results.csv"
        out_path = export_processed_to_csv(sample_processed_records, csv_file)
        assert out_path.exists()

        with csv_file.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 3
        # Check that original message and all 5 requested AI fields are present
        assert rows[0]["ticket_id"] == "TCK-101"
        assert rows[0]["raw_message"] == "The application crashes when clicking the PDF export button."
        assert rows[0]["category"] == "Bug Report"
        assert rows[0]["priority"] == "High"
        assert rows[0]["sentiment"] == "Negative"
        assert rows[0]["product_or_feature"] == "PDF Export"
        assert "investigating" in rows[0]["suggested_reply"]

        # Null feature exported as empty string in CSV
        assert rows[2]["product_or_feature"] == ""

    def test_export_processed_to_json_structure(
        self, tmp_path: Path, sample_processed_records: list[dict]
    ) -> None:
        json_file = tmp_path / "results.json"
        out_path = export_processed_to_json(sample_processed_records, json_file)
        assert out_path.exists()

        with json_file.open("r", encoding="utf-8") as f:
            data = json.load(f)

        assert len(data) == 3
        assert data[0]["ticket_id"] == "TCK-101"
        assert data[0]["category"] == "Bug Report"
        assert data[0]["priority"] == "High"
        assert data[0]["sentiment"] == "Negative"
        assert data[0]["product_or_feature"] == "PDF Export"
        assert data[2]["product_or_feature"] is None


# --- 2. All Records Export (Distinguish Ignored & Failed) ---


class TestAllRecordsExports:
    def test_export_all_records_to_csv_distinguishes_statuses(
        self, tmp_path: Path, sample_all_records: list[dict]
    ) -> None:
        csv_file = tmp_path / "all_results.csv"
        export_all_records_to_csv(sample_all_records, csv_file)

        with csv_file.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 4
        by_id = {r["ticket_id"]: r for r in rows}

        assert by_id["TCK-201"]["processing_status"] == "PROCESSED"
        assert by_id["TCK-201"]["ignore_reason"] == ""
        assert by_id["TCK-201"]["category"] == "Bug Report"

        assert by_id["TCK-202"]["processing_status"] == "IGNORED"
        assert "greeting" in by_id["TCK-202"]["ignore_reason"]
        assert by_id["TCK-202"]["category"] == ""

        assert by_id["TCK-203"]["processing_status"] == "IGNORED"
        assert "spam" in by_id["TCK-203"]["ignore_reason"]

        assert by_id["TCK-204"]["processing_status"] == "FAILED"
        assert "timeout" in by_id["TCK-204"]["ignore_reason"]

    def test_export_all_records_to_json_distinguishes_statuses(
        self, tmp_path: Path, sample_all_records: list[dict]
    ) -> None:
        json_file = tmp_path / "all_results.json"
        export_all_records_to_json(sample_all_records, json_file)

        with json_file.open("r", encoding="utf-8") as f:
            data = json.load(f)

        assert len(data) == 4
        by_id = {r["ticket_id"]: r for r in data}
        assert by_id["TCK-201"]["processing_status"] == "PROCESSED"
        assert by_id["TCK-202"]["processing_status"] == "IGNORED"
        assert by_id["TCK-204"]["processing_status"] == "FAILED"


# --- 3. Edge Cases: Empty Results & Special Characters ---


class TestExportEdgeCases:
    def test_empty_results_csv_creates_header_only_file(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "empty.csv"
        export_processed_to_csv([], csv_file)
        assert csv_file.exists()

        with csv_file.open("r", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Header only
        assert len(rows) == 1
        assert rows[0] == PROCESSED_CSV_FIELDS

    def test_empty_results_json_creates_valid_empty_array(self, tmp_path: Path) -> None:
        json_file = tmp_path / "empty.json"
        export_processed_to_json([], json_file)
        assert json_file.exists()

        with json_file.open("r", encoding="utf-8") as f:
            data = json.load(f)

        assert data == []

    def test_special_characters_quotes_newlines_unicode(self, tmp_path: Path) -> None:
        tricky_record = {
            "ticket_id": 'TCK-"TRICKY",001',
            "raw_message": (
                'Hello,\nI found a "critical" issue in the export: '
                'items with commas (a, b, c) break the CSV.\n'
                'Please test with emojis: 🚀 ⚠️ and Japanese: 日本語.'
            ),
            "category": "Bug Report",
            "priority": "High",
            "sentiment": "Negative",
            "product_or_feature": 'CSV "Export", v2',
            "suggested_reply": 'We are looking into the "CSV" issue.\nThank you! 🚀',
            "model_name": "llama-3.1-8b-instant",
            "analyzed_at": "2026-10-21T12:00:00Z",
        }

        # 1. Test CSV Round-trip
        csv_file = tmp_path / "special.csv"
        export_processed_to_csv([tricky_record], csv_file)

        with csv_file.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        read_row = rows[0]
        assert read_row["ticket_id"] == tricky_record["ticket_id"]
        assert read_row["raw_message"] == tricky_record["raw_message"]
        assert read_row["product_or_feature"] == tricky_record["product_or_feature"]
        assert read_row["suggested_reply"] == tricky_record["suggested_reply"]

        # 2. Test JSON Round-trip
        json_file = tmp_path / "special.json"
        export_processed_to_json([tricky_record], json_file)

        with json_file.open("r", encoding="utf-8") as f:
            data = json.load(f)

        assert len(data) == 1
        assert data[0]["raw_message"] == tricky_record["raw_message"]
        assert "🚀" in data[0]["suggested_reply"]
        assert "日本語" in data[0]["raw_message"]
