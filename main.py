"""
main.py
=======
Command-line entry point for the AI Customer Feedback & Support Ticket Analyzer.

Usage Examples (Windows PowerShell):
    # Analyze CSV input with real LLM:
    python main.py --input data/sample_input.csv

    # Analyze JSON input in offline mock mode (no API key needed):
    python main.py --input data/sample_input.json --mock

    # Export exclusively to JSON with debug logging:
    python main.py --input data/sample_input.csv --format json --log-level DEBUG
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from feedback_analyzer.logging_setup import setup_logging
from feedback_analyzer.orchestrator import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="feedback_analyzer",
        description="AI-Powered Customer Feedback & Support Ticket Analyzer",
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        type=str,
        help="Path to the input file (CSV or JSON format).",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["csv", "json", "both"],
        default="json",
        help="Output export format (default: 'json').",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=str,
        default=None,
        help="Directory where output CSV/JSON files are saved (default: 'output').",
    )
    parser.add_argument(
        "--db-path",
        "-d",
        type=str,
        default=None,
        help="Path to SQLite database file (default: 'output/feedback.db').",
    )
    parser.add_argument(
        "--log-level",
        "-l",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: 'INFO').",
    )
    parser.add_argument(
        "--mock",
        "-m",
        action="store_true",
        help="Run in offline / mock mode without requiring a Groq API key.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point function."""
    parser = build_parser()
    args = parser.parse_args(argv)

    input_file = Path(args.input)
    if not input_file.exists():
        print(f"Error: Input file '{args.input}' does not exist.", file=sys.stderr)
        return 1

    setup_logging(level=args.log_level)

    try:
        run_pipeline(
            input_path=input_file,
            output_dir=args.output_dir,
            db_path=args.db_path,
            export_format=args.format,
            mock_mode=args.mock,
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Pipeline execution failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
