"""
ingestion/json_reader.py
========================
Reads a JSON array file and returns each element as a plain dict.
No validation, normalisation, or business logic — only file I/O.

Raises:
    FileNotFoundError: If the file does not exist.
    ValueError: If the file extension is not .json or the root is not an array.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def read_json(path: Path) -> list[dict]:
    """
    Read a UTF-8 JSON file whose root element is an array and return the items.

    Args:
        path: Absolute or relative path to the .json file.

    Returns:
        List of dicts, one per element in the JSON array.

    Raises:
        FileNotFoundError: File does not exist at the given path.
        ValueError: File extension is not .json, or the root value is not a list.
        json.JSONDecodeError: File is not valid JSON.
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    if path.suffix.lower() != ".json":
        raise ValueError(
            f"Unsupported file type '{path.suffix}'. Expected a .json file."
        )

    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    if not isinstance(data, list):
        raise ValueError(  # noqa: TRY004
            f"JSON input must be a top-level array, got: {type(data).__name__}. "
            f"Wrap your records in a JSON array [ ... ]."
        )

    logger.debug("Read %d record(s) from JSON: %s", len(data), path.name)
    return data
