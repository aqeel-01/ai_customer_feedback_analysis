"""
unit/test_ingestion.py
======================
Tests for feedback_analyzer.ingestion (csv_reader, json_reader, dispatcher).

Covers:
  - Valid CSV and JSON files
  - FileNotFoundError for missing files
  - ValueError for unsupported file extensions
  - ValueError for JSON root that is not an array
  - Empty files (header-only CSV, empty JSON array)
  - load_records() dispatcher routing
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from feedback_analyzer.ingestion import load_records
from feedback_analyzer.ingestion.csv_reader import read_csv
from feedback_analyzer.ingestion.json_reader import read_json

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_VALID_CSV = (
    "ticket_id,message,source,created_at\n"
    "T001,App crashed on checkout.,web,2026-10-01T09:00:00Z\n"
    "T002,Please add dark mode.,mobile,2026-10-01T09:05:00Z\n"
)

_VALID_JSON = [
    {
        "ticket_id": "T001",
        "message": "App crashed on checkout.",
        "source": "web",
        "created_at": "2026-10-01T09:00:00Z",
    },
    {
        "ticket_id": "T002",
        "message": "Please add dark mode.",
        "source": "mobile",
        "created_at": "2026-10-01T09:05:00Z",
    },
]


# ---------------------------------------------------------------------------
# CSV reader
# ---------------------------------------------------------------------------


class TestCsvReader:
    def test_reads_valid_csv_returns_correct_count(self, tmp_path: Path):
        f = tmp_path / "input.csv"
        f.write_text(_VALID_CSV, encoding="utf-8")
        records = read_csv(f)
        assert len(records) == 2

    def test_reads_valid_csv_first_row_values(self, tmp_path: Path):
        f = tmp_path / "input.csv"
        f.write_text(_VALID_CSV, encoding="utf-8")
        records = read_csv(f)
        assert records[0]["ticket_id"] == "T001"
        assert records[0]["message"] == "App crashed on checkout."
        assert records[0]["source"] == "web"

    def test_reads_valid_csv_second_row_values(self, tmp_path: Path):
        f = tmp_path / "input.csv"
        f.write_text(_VALID_CSV, encoding="utf-8")
        records = read_csv(f)
        assert records[1]["ticket_id"] == "T002"
        assert records[1]["message"] == "Please add dark mode."

    def test_missing_file_raises_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            read_csv(tmp_path / "nonexistent.csv")

    def test_wrong_extension_txt_raises_value_error(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("some content", encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported"):
            read_csv(f)

    def test_wrong_extension_json_raises_value_error(self, tmp_path: Path):
        f = tmp_path / "data.json"
        f.write_text("[]", encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported"):
            read_csv(f)

    def test_header_only_csv_returns_empty_list(self, tmp_path: Path):
        f = tmp_path / "empty.csv"
        f.write_text("ticket_id,message,source,created_at\n", encoding="utf-8")
        records = read_csv(f)
        assert records == []

    def test_returns_list_of_dicts(self, tmp_path: Path):
        f = tmp_path / "input.csv"
        f.write_text(_VALID_CSV, encoding="utf-8")
        records = read_csv(f)
        assert all(isinstance(r, dict) for r in records)

    def test_uses_conftest_csv_fixture(self, csv_file: Path):
        """Smoke-test using the shared csv_file fixture from conftest."""
        records = read_csv(csv_file)
        assert len(records) == 2


# ---------------------------------------------------------------------------
# JSON reader
# ---------------------------------------------------------------------------


class TestJsonReader:
    def test_reads_valid_json_returns_correct_count(self, tmp_path: Path):
        f = tmp_path / "input.json"
        f.write_text(json.dumps(_VALID_JSON), encoding="utf-8")
        records = read_json(f)
        assert len(records) == 2

    def test_reads_valid_json_first_record_values(self, tmp_path: Path):
        f = tmp_path / "input.json"
        f.write_text(json.dumps(_VALID_JSON), encoding="utf-8")
        records = read_json(f)
        assert records[0]["ticket_id"] == "T001"
        assert records[0]["message"] == "App crashed on checkout."

    def test_missing_file_raises_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            read_json(tmp_path / "nonexistent.json")

    def test_wrong_extension_txt_raises_value_error(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("[]", encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported"):
            read_json(f)

    def test_wrong_extension_csv_raises_value_error(self, tmp_path: Path):
        f = tmp_path / "data.csv"
        f.write_text("ticket_id,message\n", encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported"):
            read_json(f)

    def test_json_object_not_array_raises_value_error(self, tmp_path: Path):
        f = tmp_path / "object.json"
        f.write_text('{"ticket_id": "T001", "message": "test"}', encoding="utf-8")
        with pytest.raises(ValueError, match="top-level array"):
            read_json(f)

    def test_empty_json_array_returns_empty_list(self, tmp_path: Path):
        f = tmp_path / "empty.json"
        f.write_text("[]", encoding="utf-8")
        records = read_json(f)
        assert records == []

    def test_returns_list_of_dicts(self, tmp_path: Path):
        f = tmp_path / "input.json"
        f.write_text(json.dumps(_VALID_JSON), encoding="utf-8")
        records = read_json(f)
        assert all(isinstance(r, dict) for r in records)

    def test_uses_conftest_json_fixture(self, json_file: Path):
        """Smoke-test using the shared json_file fixture from conftest."""
        records = read_json(json_file)
        assert len(records) == 2


# ---------------------------------------------------------------------------
# load_records dispatcher
# ---------------------------------------------------------------------------


class TestLoadRecordsDispatcher:
    def test_dispatches_csv_extension(self, tmp_path: Path):
        f = tmp_path / "input.csv"
        f.write_text(_VALID_CSV, encoding="utf-8")
        records = load_records(f)
        assert len(records) == 2

    def test_dispatches_json_extension(self, tmp_path: Path):
        f = tmp_path / "input.json"
        f.write_text(json.dumps(_VALID_JSON), encoding="utf-8")
        records = load_records(f)
        assert len(records) == 2

    def test_unsupported_xlsx_extension_raises_value_error(self, tmp_path: Path):
        f = tmp_path / "data.xlsx"
        f.write_text("binary content", encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported"):
            load_records(f)

    def test_unsupported_txt_extension_raises_value_error(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("some text", encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported"):
            load_records(f)

    def test_dispatches_via_conftest_csv_fixture(self, csv_file: Path):
        records = load_records(csv_file)
        assert len(records) == 2

    def test_dispatches_via_conftest_json_fixture(self, json_file: Path):
        records = load_records(json_file)
        assert len(records) == 2
