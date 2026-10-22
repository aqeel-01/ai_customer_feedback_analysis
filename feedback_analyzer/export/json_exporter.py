"""
export/json_exporter.py
=======================
Exports feedback analysis records to formatted JSON.
Handles Unicode characters, empty result sets, and structure formatting safely.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def export_processed_to_json(
    records: Sequence[dict[str, Any]],
    output_path: str | Path,
    indent: int = 2,
) -> Path:
    """
    Write successfully processed feedback tickets to a JSON array file.

    Includes the original message and all 5 AI-extracted fields:
    category, priority, sentiment, product_or_feature, suggested_reply.

    Args:
        records: List of dictionaries of processed tickets.
        output_path: Destination path for the JSON file.
        indent: Indentation level for pretty-printing.

    Returns:
        Path object of the written file.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(list(records), f, indent=indent, ensure_ascii=False)

    return path


def export_all_records_to_json(
    records: Sequence[dict[str, Any]],
    output_path: str | Path,
    indent: int = 2,
) -> Path:
    """
    Write all tickets (PROCESSED, IGNORED, INVALID, FAILED) to a JSON file.
    Keeps ignored, invalid, and failed records distinct with reasons and statuses.

    Args:
        records: List of dictionaries of all tickets.
        output_path: Destination path for the JSON file.
        indent: Indentation level for pretty-printing.

    Returns:
        Path object of the written file.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(list(records), f, indent=indent, ensure_ascii=False)

    return path
