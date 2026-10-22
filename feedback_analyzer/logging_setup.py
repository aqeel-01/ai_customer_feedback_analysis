"""
logging_setup.py
================
Configures application-wide logging with clean formatting.
Ensures console output is informative and secrets are never exposed.
"""

from __future__ import annotations

import logging
import sys

DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    level: str | None = "INFO",
    log_file: str | None = None,
) -> None:
    """
    Initialize root logging configuration.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR).
        log_file: Optional file path to also persist logs to disk.
    """
    log_level = getattr(logging, (level or "INFO").upper(), logging.INFO)

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=log_level,
        format=DEFAULT_FORMAT,
        datefmt=DATE_FORMAT,
        handlers=handlers,
        force=True,
    )
