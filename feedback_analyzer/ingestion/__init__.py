"""
ingestion package
=================
Reads raw input files (CSV or JSON) and returns each record as a plain dict.
No validation, filtering, or business logic occurs here.

Public API:
    load_records(path) -> list[dict]
        Dispatches to read_csv or read_json based on file extension.
"""

from __future__ import annotations

import logging
from pathlib import Path

from feedback_analyzer.ingestion.csv_reader import read_csv
from feedback_analyzer.ingestion.json_reader import read_json

logger = logging.getLogger(__name__)

_SUPPORTED_EXTENSIONS = {".csv", ".json"}


def load_records(path: Path) -> list[dict]:
    """
    Load raw records from a CSV or JSON file.

    Dispatches to the appropriate reader based on the file extension.

    Args:
        path: Path to the input file (.csv or .json).

    Returns:
        List of dicts, one per record.

    Raises:
        FileNotFoundError: File does not exist.
        ValueError: File extension is not .csv or .json.
    """
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".csv":
        return read_csv(path)
    elif suffix == ".json":
        return read_json(path)
    else:
        supported = ", ".join(sorted(_SUPPORTED_EXTENSIONS))
        raise ValueError(
            f"Unsupported file format '{suffix}'. Supported formats: {supported}. "
            f"Got: {path.name}"
        )
