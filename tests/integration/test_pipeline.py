"""
integration/test_pipeline.py
============================
End-to-end integration tests for the full feedback analyzer pipeline.
Uses mocked LLM responses and in-memory or temporary SQLite databases.
Covers:
  - Reading CSV and JSON sample inputs
  - Validation failures handled gracefully without stopping the pipeline
  - Filtering non-qualifying tickets (greetings and spam)
  - LLM classification and structured extraction
  - LLM API failure handling (recorded as FAILED, pipeline continues)
  - Duplicate detection and skipping
  - Database persistence and export generation (CSV & JSON)
  - Summary metrics accuracy
  - CLI execution via main()
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from feedback_analyzer.config import Config
from feedback_analyzer.db.connection import get_connection
from feedback_analyzer.db.repository import (
    list_all_tickets_with_results,
    list_processed_tickets,
)
from feedback_analyzer.orchestrator import MockTicketAnalyzer, run_pipeline
from main import main


@pytest.fixture
def test_config(tmp_path: Path) -> Config:
    return Config(
        groq_api_key="gsk_mock_test_key_pipeline",
        model_name="llama-3.1-8b-instant",
        db_path=str(tmp_path / "test_feedback.db"),
        output_dir=str(tmp_path / "output"),
    )


class TestFullPipelineEndToEnd:
    def test_run_pipeline_on_sample_csv_in_mock_mode(
        self, tmp_path: Path, test_config: Config
    ) -> None:
        input_csv = Path("data/sample_input.csv")
        assert input_csv.exists(), "Sample input CSV must exist"

        db_file = tmp_path / "csv_run.db"
        out_dir = tmp_path / "csv_out"

        summary = run_pipeline(
            input_path=input_csv,
            output_dir=out_dir,
            db_path=db_file,
            export_format="both",
            mock_mode=True,
            config=test_config,
        )

        # sample_input.csv has 15 records (10 actionable, 5 greetings/spam):
        assert summary.total_records == 15
        assert summary.valid_records == 15
        assert summary.invalid_records == 0
        assert summary.ignored_records == 5
        assert summary.processed_records == 10
        assert summary.failed_records == 0
        assert summary.skipped_duplicates == 0

        # Verify DB records
        conn = get_connection(db_file)
        processed = list_processed_tickets(conn)
        assert len(processed) == 10

        all_records = list_all_tickets_with_results(conn)
        assert len(all_records) == 15
        conn.close()

        # Verify exports exist and are valid
        assert (out_dir / "results.csv").exists()
        assert (out_dir / "results.json").exists()
        assert (out_dir / "all_tickets.csv").exists()
        assert (out_dir / "all_tickets.json").exists()

        with (out_dir / "results.csv").open("r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
            assert len(reader) == 10
            # Confirm all 5 AI fields + message are present
            first = reader[0]
            assert "raw_message" in first
            assert "category" in first
            assert "priority" in first
            assert "sentiment" in first
            assert "product_or_feature" in first
            assert "suggested_reply" in first

    def test_run_pipeline_on_sample_json_in_mock_mode(
        self, tmp_path: Path, test_config: Config
    ) -> None:
        input_json = Path("data/sample_input.json")
        assert input_json.exists(), "Sample input JSON must exist"

        db_file = tmp_path / "json_run.db"
        out_dir = tmp_path / "json_out"

        summary = run_pipeline(
            input_path=input_json,
            output_dir=out_dir,
            db_path=db_file,
            export_format="json",
            mock_mode=True,
            config=test_config,
        )

        assert summary.total_records == 15
        assert summary.processed_records == 10
        assert summary.ignored_records == 5

        with (out_dir / "results.json").open("r", encoding="utf-8") as f:
            data = json.load(f)
            assert len(data) == 10
            categories = {item["category"] for item in data}
            assert "Bug Report" in categories
            assert "Feature Request" in categories

    def test_pipeline_continues_when_record_is_invalid(
        self, tmp_path: Path, test_config: Config
    ) -> None:
        # Create CSV with an invalid row in the middle
        mixed_csv = tmp_path / "mixed.csv"
        mixed_csv.write_text(
            "ticket_id,message\n"
            "T-100,Application crashed on checkout\n"
            ",Missing ID record\n"  # Invalid: blank ticket_id
            "T-102,   \n"  # Invalid: blank message
            'T-103,"Hi, please add dark mode to the app"\n',
            encoding="utf-8",
        )

        db_file = tmp_path / "invalid_test.db"
        out_dir = tmp_path / "invalid_out"

        summary = run_pipeline(
            input_path=mixed_csv,
            output_dir=out_dir,
            db_path=db_file,
            mock_mode=True,
            config=test_config,
        )

        assert summary.total_records == 4
        assert summary.valid_records == 2
        assert summary.invalid_records == 2
        assert summary.processed_records == 2

        conn = get_connection(db_file)
        all_records = list_all_tickets_with_results(conn)
        assert len(all_records) == 4
        statuses = [r["processing_status"] for r in all_records]
        assert statuses.count("INVALID") == 2
        assert statuses.count("PROCESSED") == 2
        conn.close()

    def test_pipeline_continues_when_llm_fails_on_single_record(
        self, tmp_path: Path, test_config: Config
    ) -> None:
        mixed_csv = tmp_path / "fail_test.csv"
        mixed_csv.write_text(
            "ticket_id,message\n"
            "T-201,The payment gateway is broken\n"
            "T-202,Crash on save report\n",
            encoding="utf-8",
        )

        mock_analyzer = MagicMock()
        # First call fails, second call succeeds
        mock_analyzer.analyze.side_effect = [
            RuntimeError("Simulated LLM rate limit or network error"),
            MockTicketAnalyzer().analyze(
                MagicMock(ticket_id="T-202", message="Crash on save report", created_at=None)
            ),
        ]

        db_file = tmp_path / "llm_fail.db"
        out_dir = tmp_path / "llm_fail_out"

        summary = run_pipeline(
            input_path=mixed_csv,
            output_dir=out_dir,
            db_path=db_file,
            analyzer=mock_analyzer,
            config=test_config,
        )

        assert summary.total_records == 2
        assert summary.failed_records == 1
        assert summary.processed_records == 1

        conn = get_connection(db_file)
        all_records = list_all_tickets_with_results(conn)
        assert len(all_records) == 2
        by_id = {r["ticket_id"]: r for r in all_records}
        assert by_id["T-201"]["processing_status"] == "FAILED"
        assert "Simulated LLM" in by_id["T-201"]["ignore_reason"]
        assert by_id["T-202"]["processing_status"] == "PROCESSED"
        conn.close()

    def test_duplicate_tickets_skipped_on_rerun(
        self, tmp_path: Path, test_config: Config
    ) -> None:
        input_csv = Path("data/sample_input.csv")
        db_file = tmp_path / "dup_run.db"
        out_dir = tmp_path / "dup_out"

        # First run
        run_1 = run_pipeline(
            input_path=input_csv,
            output_dir=out_dir,
            db_path=db_file,
            mock_mode=True,
            config=test_config,
        )
        assert run_1.processed_records == 10
        assert run_1.skipped_duplicates == 0

        # Second run with exact same file -> all records already exist and should be skipped
        run_2 = run_pipeline(
            input_path=input_csv,
            output_dir=out_dir,
            db_path=db_file,
            mock_mode=True,
            config=test_config,
        )
        assert run_2.skipped_duplicates == 15
        assert run_2.processed_records == 0

    def test_cli_main_entry_point(self, tmp_path: Path) -> None:
        db_file = tmp_path / "cli_test.db"
        out_dir = tmp_path / "cli_out"

        exit_code = main([
            "--input", "data/sample_input.csv",
            "--output-dir", str(out_dir),
            "--db-path", str(db_file),
            "--format", "both",
            "--mock",
        ])

        assert exit_code == 0
        assert (out_dir / "results.csv").exists()
        assert (out_dir / "results.json").exists()

    def test_cli_main_nonexistent_file_returns_error_code(self) -> None:
        exit_code = main(["--input", "non_existent_file.csv"])
        assert exit_code == 1
