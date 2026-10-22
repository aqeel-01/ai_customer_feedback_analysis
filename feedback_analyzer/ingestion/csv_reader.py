"""
ingestion/csv_reader.py
=======================
Reads a CSV file and returns each data row as a plain dict.
No validation, normalisation, or business logic — only file I/O.

Raises:
    FileNotFoundError: If the file does not exist.
    ValueError: If the file extension is not .csv.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def read_csv(path: Path) -> list[dict]:
    """
    Read a UTF-8 CSV file and return all rows as a list of dicts.

    The CSV must have a header row. Rows are returned in file order.
    Empty files (header only) return an empty list.

    Args:
        path: Absolute or relative path to the .csv file.

    Returns:
        List of dicts, one per data row, keyed by the header names.

    Raises:
        FileNotFoundError: File does not exist at the given path.
        ValueError: File extension is not .csv.
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    if path.suffix.lower() != ".csv":
        raise ValueError(
            f"Unsupported file type '{path.suffix}'. Expected a .csv file."
        )

    rows: list[dict] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(dict(row))

    logger.debug("Read %d row(s) from CSV: %s", len(rows), path.name)
    return rows
